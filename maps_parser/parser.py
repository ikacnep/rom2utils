import os
import struct
import sys

import a2data


class ParseException(Exception):
	pass


class GenericParser:
	def __init__(self, data):
		self.data = data
		self.p = 0

	def eat(self, fmt):
		size = fmt.size()
		content = struct.unpack(fmt.as_struct(), self.data[self.p:self.p+size])
		self.p += size
		return fmt.from_unpacked(content)


class Parser(GenericParser):
	def parse(self) -> a2data.AllodsMap:
		header = self.eat(a2data.Header())
		
		if header.signature != a2data.alm_signature:
			raise ParseException(f'incorrect signature: {header.signature}')
		if header.version != a2data.alm_version:
			raise ParseException(f'unhandled version: {header.version} != {a2data.alm_version}')

		section_signature = None

		tiles, heights, objects, buildings, players = [], [], [], [], []

		for s in range(header.num_sections):
			section_header = self.eat(a2data.SectionHeader())

			if section_signature is None:
				section_signature = section_header.signature

			if section_header.signature != section_signature:
				raise ParseException(f'incorrect section signature: {section_header.signature} != {section_signature} around p={self.p}')

			if 0 <= section_header.id <= 5:
				section_type = getattr(a2data, f'Section{section_header.id}')
				stop_at = self.p + section_header.section_size

				while self.p < stop_at:
					section = self.eat(section_type())
					if section_header.id == 0:
						info = section
					elif section_header.id == 1:
						tiles.append(section.tile)
					elif section_header.id == 2:
						heights.append(section.height)
					elif section_header.id == 3:
						objects.append(section.object_id)
					elif section_header.id == 4:
						if section.type_id >= 0x1000000:
							bridge_size = self.eat(a2data.BridgeSize())
							section.bridge_width = bridge_size.bridge_width
							section.bridge_height = bridge_size.bridge_height

						buildings.append(section)
					elif section_header.id == 5:
						players.append(section)
			elif section_header.id == 6:
				units = self.parse_units(info.num_units)
			elif section_header.id == 7:
				instances, checks, triggers = self.parse_logics()
			elif section_header.id == 8:
				bags = self.parse_bags(info.num_bags)
			elif section_header.id == 9:
				effects = self.parse_effects()
			elif section_header.id == 10:
				groups = self.parse_groups(info.num_groups)
			elif section_header.id == 11:
				inns, shops, signs = self.parse_shops(info.num_inns, info.num_shops, info.num_signs)
			elif section_header.id == 12:
				music = self.parse_music(info.num_music)
			else:
				raise ParseException('unhandled section with id {section_header.id}')

		if self.p != len(self.data):
			raise ParseException(f'trailing data: {self.p} != {len(self.data)}')
		return a2data.AllodsMap(info, tiles, heights, objects, units, buildings, players, instances, checks, triggers, bags, effects, groups, inns, shops, signs, music)

	def parse_effects(self):
		section = self.eat(a2data.Effects())
		effects = []
		for i in range(section.num_effects):
			effect = self.eat(a2data.Effect())
			effect.modifiers = [self.eat(a2data.EffectModifier()) for j in range(effect.num_modifiers)]
			effects.append(effect)
		return effects

	def parse_shops(self, num_inns, num_shops, num_signs):
		inns = [self.eat(a2data.Inn()) for i in range(num_inns)]
		shops = [self.eat(a2data.Shop()) for i in range(num_shops)]
		signs = [self.eat(a2data.Sign()) for i in range(num_signs)]
		return inns, shops, signs

	def parse_bags(self, num_bags):
		bags = []
		for i in range(num_bags):
			bag = self.eat(a2data.Bag())
			bag.items = [self.eat(a2data.BagItem()) for j in range(bag.num_items)]
			bags.append(bag)
		return bags

	def parse_units(self, num_units):
		return [self.eat(a2data.Unit()) for i in range(num_units)]

	def parse_logics(self):
		num_instances = self.eat(a2data.Instances()).num_instances
		instances = [self.eat(a2data.Instance()) for i in range(num_instances)]
		instances_dict = {e.index: e for e in instances}
		if len(instances) != len(instances_dict):
			raise ParseException(f'some instances have the same index: s{len(instances)} != {len(instances_dict)}: {instances}')

		num_checks = self.eat(a2data.Instances()).num_instances
		checks = [self.eat(a2data.Instance()) for i in range(num_checks)]
		checks_dict = {e.index: e for e in checks}
		if any(x != 0 for x in checks_dict):
			if len(checks) != len(checks_dict):
				raise ParseException(f'checks are not unique: {len(checks)} != {len(checks_dict)}: {checks}')

		num_triggers = self.eat(a2data.Instances()).num_instances
		triggers = [self.eat(a2data.Trigger()) for i in range(num_triggers)]

		return instances_dict, checks_dict, triggers

	def parse_groups(self, num_groups):
		return [self.eat(a2data.Group()) for i in range(num_groups)]

	def parse_music(self, num_music):
		return [self.eat(a2data.Music()) for i in range(num_music + 1)]


def parse(f) -> a2data.AllodsMap:
	with open(f, 'rb') as inf:
		try:
			return Parser(inf.read()).parse()
		except Exception as error:
			raise ParseException(f'failed to parse {f!r}') from error


class ThatsEnough(Exception):
	pass


class UnitKindParser(GenericParser):
	def __init__(self, databin):
		super().__init__(databin)

		first_unit = databin.index(b'Catapult') - 1
		self.p = first_unit

	def parse(self):
		return list(self._while(self.parse_monster)) + list(self._while(self.parse_human))

	def parse_monster(self):
		name = self.eat_var_string()
		unit = self.eat(a2data.UnitMonster())
		unit.name = name

		if unit.kingdom != 62:
			raise ParseException(f'monster does not have kingdom 62: {unit}')

		if unit.name == 'Human':
			self.p = self.data.find(b'Man_Unarmed', self.p) - 1
			return

		unit.items = list(self._while(self.eat_var_string))

		while self.data[self.p] == 0:
			self.p += 1

		return unit

	def parse_human(self):
		name = self.eat_var_string()
		unit = self.eat(a2data.UnitHuman())
		unit.name = name

		if unit.kingdom != 26:
			raise ParseException(f'human does not have kingdom 26: {unit}')

		try:
			unit.items = list(self._while(self.eat_item_name))
			while self.data[self.p+self.data[self.p]+1:self.p+self.data[self.p]+3] != b'\x1A\x00':
				new_items = list(self._while(self.eat_item_name))
				unit.items += new_items
		except ThatsEnough:
			return

		while self.data[self.p] == 0:
			self.p += 1

		return unit

	def _while(self, act):
		while True:
			thing = act()
			if not thing:
				break
			yield thing

	def eat_var_bytes(self):
		size = int(self.data[self.p])
		self.p += 1

		s = self.data[self.p:self.p+size]
		self.p += size

		return s

	def eat_var_string(self):
		s = self.eat_var_bytes()
		if 0 in s:
			raise ParseException(f'string with a zero: {s}')
		return s.decode('utf-8')

	def eat_item_name(self):
		s = self.eat_var_bytes()

		if len(s) > 100 and 0 in s:
			raise ThatsEnough()

		if self.data[self.p:self.p+2] == b'\x1A\x00':
			self.p -= len(s) + 1
			return

		return s.decode('utf-8')


class EngineData:
	def __init__(self, item_names, spell_names, item_modifiers, unit_kinds):
		self.item_names = item_names
		self.spell_names = spell_names
		self.item_modifiers = item_modifiers
		self.unit_kinds = unit_kinds

	def unit_name(self, server_id):
		if server_id in self.unit_kinds:
			return self.unit_kinds[server_id].name
		return f'(!failed to find unit: server_id={server_id})'


def parse_engine_data(data_directory, filenames) -> EngineData:
	if not data_directory:
		if not filenames:
			raise Exception('specify --allods_data_directory')

		d = os.path.abspath(os.path.dirname(filenames[0]))
		while d != os.path.dirname(d):
			if os.path.exists(os.path.join(d, 'data/world/data/itemname.bin')):
				data_directory = os.path.join(d, 'data')
				break
			d = os.path.dirname(d)
		if not data_directory:
			raise Exception('failed to determine data directory, specify --allods_data_directory')

	with open(os.path.join(data_directory, 'world/data/itemname.bin'), 'rb') as inf:
		itemname_bin = inf.read()

	item_ids = []
	for i in range(0, len(itemname_bin), 2):
		item_ids.append(itemname_bin[i+1] << 8 | itemname_bin[i])

	with open(os.path.join(data_directory, 'locale/en/itemname.txt'), 'r', encoding='cp1251') as inf:
		itemserv = inf.read().strip()

	item_names = itemserv.split('\n')

	if len(item_ids) != len(item_names):
		raise ParseException(f'item ID and item name lists have different size: {len(item_ids)} != {len(item_names)}')

	item_map = {}
	for i, item_id in enumerate(item_ids):
		item_map[a2data.Hex(item_id)] = item_names[i]

	with open(os.path.join(data_directory, 'locale/en/spell.txt'), 'r', encoding='cp1251') as inf:
		spell = inf.read().strip()
	spell_names = spell.split('\n')

	item_modifiers = [
		'none',
		'price',
		'body',
		'mind',
		'reaction',
		'spirit',
		'health',
		'healthmax',
		'healthregeneration',
		'mana',
		'manamax',
		'manaregeneration',
		'tohit',
		'damagemin',
		'damagemax',
		'defence',
		'absorbtion',
		'speed',
		'rotationspeed',
		'scanrange',
		'protection0',
		'protectionfire',
		'protectionwater',
		'protectionair',
		'protectionearth',
		'protectionastral',
		'fighterskill0',
		'skillblade',
		'skillaxe',
		'skillbludgeon',
		'skillpike',
		'skillshooting',
		'mageskill0',
		'skillfire',
		'skillwater',
		'skillair',
		'skillearth',
		'skillastral',
		'itemlore',
		'magiclore',
		'creaturelore',
		'damagebonus',
	]

	with open(os.path.join(data_directory, 'world/data/data.bin'), 'rb') as inf:
		databin = inf.read().strip()
	unit_kinds = parse_databin(databin)

	return EngineData(item_map, spell_names, item_modifiers, unit_kinds)


def parse_databin(databin):
	units = UnitKindParser(databin).parse()

	unit_kinds = {unit.server_id: unit for unit in units}
	if len(units) != len(unit_kinds):
		raise ParseException(f'some units have the same server_id: {len(units)} != {len(unit_kinds)}: {units}')

	return unit_kinds
