# TODO: this crap is too interdependent.

import functools
import struct
from typing import Dict, List, Optional


alm_signature = b'M7R\x00'
alm_version = 1600


class Hex(int):
	def __str__(self):
		return '0x%0X' % self
	def __repr__(self):
		return self.__str__()


def _byte(value):
	return bytes(value.to_bytes(1, 'big'))


class Format():
	def __init__(self, **kwargs) -> None:
		have_keys = {k for k in self.__class__.__dict__.keys() if not k.startswith('_')}

		for k, v in kwargs.items():
			if k not in have_keys:
				raise Exception(f'{self.__class__} does not have a key {k}')
			setattr(self, k, v)
	
	@staticmethod
	def _symbol(data_type):
		if isinstance(data_type, bytes):
			return 'c' * len(data_type)
		if isinstance(data_type, str):
			return 'c' * int(data_type)
		if isinstance(data_type, int):
			try:
				res = '-BH-I'[int(data_type)]
			except:
				print(data_type)
				raise
			assert res != '-', f'int({data_type}) is unsupported'
			return res
		if isinstance(data_type, list):
			return ''.join(Format._symbol(e) for e in data_type)
		if data_type is None:
			return ''

		assert False, f'type {type(data_type)} is not supported in Format._symbol'

	@classmethod
	@functools.lru_cache
	def as_struct(cls):
		# Note that this doesn't iterate over `as_struct`, `from_unpacked` and other similar
        # methods because they're class methods or static methods. Yeah, it's weird.
		return '<' + ''.join(Format._symbol(v) for k, v in cls.__dict__.items() if not k.startswith('_'))

	@classmethod
	def size(cls):
		return struct.calcsize(cls.as_struct())

	@staticmethod
	def _unpack(data_type, unpacked, pos):
		if isinstance(data_type, bytes):
			return b''.join(unpacked[pos:pos+len(data_type)]), len(data_type)
		elif isinstance(data_type, str):
			s = b''.join(unpacked[pos:pos+int(data_type)])
			if b'\x00' in s:
				s = s[:s.index(b'\x00')]
			return s.decode('cp1251'), int(data_type)
		elif isinstance(data_type, Hex):
			return Hex(unpacked[pos]), 1
		elif isinstance(data_type, int):
			return unpacked[pos], 1
		elif isinstance(data_type, list):
			res = []
			delta = 0
			for i in range(len(data_type)):
				raw = data_type[i]
				value, plus = Format._unpack(raw, unpacked, pos + delta)
				res.append(value)
				delta += plus
			return res, delta
		elif data_type is None:
			return None, 0
		else:
			assert False, f'type {type(data_type)} is not supported in Format._unpack'

	@staticmethod
	def _pack(data_type, value):
		if isinstance(data_type, bytes):
			size = len(data_type)
			return list(_byte(c) for c in value) + [b'\0'] * (size - len(value))
		elif isinstance(data_type, str):
			size = int(data_type)
			return list(_byte(c) for c in value.encode('cp1251')) + [b'\0'] * (size - len(value))
		elif isinstance(data_type, int):
			return [value]
		elif isinstance(data_type, list):
			res = []
			assert len(data_type) == len(value), f'object has wrong element count: type={data_type!r}, value={value!r}'
			for i in range(len(data_type)):
				val = Format._pack(data_type[i], value[i])
				res.extend(val)
			return res
		elif data_type is None:
			return []
		else:
			assert False, f'type {type(data_type)} (value {data_type!r}) is not supported in Format._pack'

	@classmethod
	def from_unpacked(cls, unpacked):
		i = 0
		new = cls()
		for k, v in cls.__dict__.items():
			if not k.startswith('_'):
				value, delta = Format._unpack(v, unpacked, i)
				i += delta
				setattr(new, k, value)
		new._from_alm()
		return new

	@classmethod
	def to_packed(cls, value):
		res = []

		value._to_alm()
		for k, v in cls.__dict__.items():
			if not k.startswith('_'):
				res.extend(Format._pack(v, getattr(value, k)))

		value._from_alm()

		return res

	def _from_alm(self):
		pass

	def _to_alm(self):
		pass

	def __str__(self):
		res = []
		for k, v in self.__dict__.items():
			res.append(f'{k}: {v}')
		return ', '.join(res)

	def __repr__(self):
		return self.__str__()


def coordinate_from_alm(c):
	c = c - 128
	assert c % 256 == 0
	c = c // 256
	assert c >= 0
	return c


def coordinate_to_alm(c):
	return c * 256 + 128


class Coordinate():
	def _from_alm(self):
		self.x = coordinate_from_alm(self.x)
		self.y = coordinate_from_alm(self.y)

	def _to_alm(self):
		self.x = coordinate_to_alm(self.x)
		self.y = coordinate_to_alm(self.y)


class Header(Format):
	signature = bytes(4)
	alm_size = int(4)
	something_0 = int(4)
	num_sections = int(4)
	version = int(4)


class SectionHeader(Format):
	seven_or_five = int(4)
	alm_size = int(4)
	section_size = int(4)
	id = int(4)
	signature = Hex(4)


class GenericInfo(Format):
	width = int(4)
	height = int(4)
	sun_angle = int(4)
	time_of_day = int(4)
	darkness = int(4)
	contrast = int(4)
	use_tiles = int(4)
	num_players = int(4)
	num_buildings = int(4)
	num_units = int(4)
	num_logic = int(4)
	num_bags = int(4)
	num_groups = int(4)
	num_inns = int(4)
	num_shops = int(4)
	num_signs = int(4)
	num_music = int(4)
	map_name = str(64)
	recommended_players = int(4)
	map_level = int(4)
	something_1 = int(4)
	something_2 = int(4)
	author_name = str(512)
Section0 = GenericInfo


class Landscape(Format):
	tile = Hex(2)
Section1 = Landscape


class Height(Format):
	height = int(1)
Section2 = Height


class Object(Format):
	object_id = int(1)
Section3 = Object


class Building(Coordinate, Format):
	x = int(4)
	y = int(4)
	type_id = int(4)
	health = int(2)
	player = int(4)
	building_id = int(2)
	bridge_width = None
	bridge_height = None
Section4 = Building


class BridgeSize(Format):
	bridge_width = int(4)
	bridge_height = int(4)


class Player(Format):
	color = int(4)
	flags = Hex(4)
	money = int(4)
	name = str(32)
	diplomacy = [Hex(2)] * 16
Section5 = Player


class Unit(Coordinate, Format):
	x = int(4)
	y = int(4)
	type_id = int(2)
	face = int(2)
	flags = Hex(4)
	more_flags = Hex(4)
	server_id = int(4)
	player_id = int(4)
	bag_id = int(4)
	rotation = int(4)
	hp = int(2)
	max_hp = int(2)
	unit_id = int(2)
	something_3 = Hex(2)
	group_id = int(4)


class Instances(Format):
	num_instances = int(4)


class Instance(Format):
	name = str(64)
	type_id = int(4)
	index = int(4)
	execute_once = int(4)
	arg_value = [int(4)] * 10
	arg_type = [int(4)] * 10
	arg_name = [str(64)] * 10


class Trigger(Format):
	name = str(128)
	check_ids = [int(4)] * 6
	instance_ids = [int(4)] * 4
	check_operators = [int(4)] * 3
	execute_once = int(4)


class Bag(Coordinate, Format):
	num_items = int(4)
	unit_id = int(4)
	x = int(4)
	y = int(4)
	gold = int(4)
	items = None


class BagItem(Format):
	item_id = Hex(4)
	wielded = int(2)
	effect = int(4)


class Effects(Format):
	num_effects = int(4)
Section9 = Effects


class Group(Format):
	group_id = int(4)
	repop_time = int(4)
	flags = Hex(4)
	instance_id = int(4)


class Effect(Format):
	range = int(4)
	x = int(4)
	y = int(4)
	magic_type = int(2)
	min_magic_damage = int(2)
	max_magic_damage = int(2)
	spell_type_id = int(2)
	spell_power = int(2)
	num_modifiers = int(4)
	modifiers = None


class EffectModifier(Format):
	x = int(2)
	y = int(2)
	flags = int(2)


class Inn(Format):
	inn_id = int(4)
	flags = Hex(4)
	delivery_item_id = Hex(4)


class Shop(Format):
	shop_id = int(4)
	shelf_flags = [Hex(4)] * 4
	min_price = [int(4)] * 4
	max_price = [int(4)] * 4
	max_items = [int(4)] * 4
	max_same_type_items = [int(4)] * 4


class Sign(Format):
	sign_id = int(4)
	flags = Hex(4)
	instance_id = int(4)


class Music(Format):
	x = int(4)
	y = int(4)
	radius = int(4)
	melody_type_id = [int(4)] * 4


class UnitMonster(Format):
	name = None
	kingdom = int(2)
	body = int(4)
	reaction = int(4)
	mind = int(4)
	spirit = int(4)
	hp = int(4)
	hp_regen = int(4)
	mana = int(4)
	mana_regen = int(4)
	speed = int(4)
	rotation_speed = int(4)
	scan_range = int(4)
	damage_min = int(4)
	damage_max = int(4)
	attack_type = int(4)
	attack = int(4)
	defence = int(4)
	armor = int(4)
	charge = int(4)
	relax = int(4)
	resist_magic = [int(4)] * 5
	resist_weapon = [int(4)] * 5
	type_id = int(4)
	face = int(4)
	token_size = int(4)
	movement_type = int(4)
	dying_time = int(4)
	withdraw = int(4)
	wimpy = int(4)
	detection_range = int(4)
	experience = int(4)
	gold = int(4)
	gold_min = int(4)
	gold_max = int(4)
	drop = int(4)
	drop_price_min = int(4)
	drop_price_max = int(4)
	drop_mask = Hex(4)
	something_27 = int(4)
	something_28 = int(4)
	power = int(4)
	spell_1 = int(4)
	spell_probability_1 = int(4)
	spell_2 = int(4)
	spell_probability_2 = int(4)
	spell_3 = int(4)
	spell_probability_3 = int(4)
	spell_power = int(4)
	server_id = int(4)
	known_spells = Hex(4)
	skills = [int(4)] * 5
	items = None


class UnitHuman(Format):
	name = None
	kingdom = int(2)
	body = int(4)
	reaction = int(4)
	mind = int(4)
	spirit = int(4)
	hp = int(4)
	mana = int(4)
	speed = int(4)
	rotation_speed = int(4)
	scan_range = int(4)
	defence = int(4)
	main_skill = int(4)
	skills = [int(4)] * 5
	type_id = int(4)
	face = int(4)
	gender = int(4)
	charge_time = int(4)
	relax_time = int(4)
	token_size = int(4)
	movement_type = int(4)
	dying_time = int(4)
	server_id = int(4)
	known_spells = Hex(4)
	items = None


class AllodsMap(Format):
	# Need this stuff for JSON deserialization.
	info = None
	tiles = None
	heights = None
	objects = None
	units = None
	buildings = None
	players = None
	instances = None
	checks = None
	triggers = None
	bags = None
	effects = None
	groups = None
	inns = None
	shops = None
	signs = None
	music = None
	
	def __init__(
			self,
			info: GenericInfo,
			tiles: List[int],
			heights: List[int],
			objects: List[int],
			units: List[Unit],
			buildings: List[Building],
			players: List[Player],
			instances: Dict[int, Instance],
			checks: Dict[int, Instance],
			triggers: List[Trigger],
			bags: List[Bag],
			effects: List[Effect],
			groups: List[Group],
			inns: List[Inn],
			shops: List[Shop],
			signs: List[Sign],
			music: List[Music],
	):
		self.info = info
		self.tiles = tiles
		self.heights = heights
		self.objects = objects
		self.units = units
		self.buildings = buildings
		self.players = players
		self.instances = instances
		self.checks = checks
		self.triggers = triggers
		self.bags = bags
		self.effects = effects
		self.groups = groups
		self.inns = inns
		self.shops = shops
		self.signs = signs
		self.music = music
