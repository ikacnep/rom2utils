#!/usr/bin/env python3

import argparse
from colorama import Fore, Back, Style
import collections
import io
import json
import os
import re
import shutil
import sys

import a2data
import marshaller
import parser


def color_amount(amount):
	return Fore.YELLOW + str(amount) + Style.RESET_ALL


def color_magic(amount):
	return Fore.BLUE + str(amount) + Style.RESET_ALL


def color_modifier(amount):
	return Fore.MAGENTA + str(amount) + Style.RESET_ALL


def color_error(amount):
	return Fore.RED + str(amount) + Style.RESET_ALL


def color_reference(amount):
	return Fore.GREEN + str(amount) + Style.RESET_ALL


def spell(engine_data: parser.EngineData, spell_id: int, power: int):
	if spell_id == 0:
		return ''

	spell = engine_data.spell_names[spell_id - 1]
	res = color_magic(spell)
	if power:
		res += f' at level {power}'
	return res


def unit_param_check(args):
	assert args[1] == 6, f'unit param check with param != 6: {args}'
	return f'unit_health({args[0]})'


def unit_param_instance(args, e):
	assert args[1] == 6, f'unit param instance with param != 6: {args}'
	return f'unit_health({args[0]}) := {args[2]}'


checks = {
	0: lambda args: '(!broken check: type_id = 0)',
	1: lambda args: f'count_units(group={args[0]})',
	2: lambda args: f'is_unit_in_box({args[0]}, left={args[1]}, top={args[2]}, right={args[3]}, bottom={args[4]})',
	3: lambda args: f'is_unit_in_circle({args[0]}, x={args[1]}, y={args[2]}, radius={args[3]})',
	4: unit_param_check,
	5: lambda args: f'unit_alive({args[0]})',
	19: lambda args: f'variable({args[0]})',
	21: lambda args: f'building_health({args[0]})',
	65538: lambda args: f'{args[0]}',
}
def render_check(check_id, map_info):
	c = map_info.checks.get(check_id)
	if not c:
		return f'(!broken check {check_id})'
	try:
		return f'{checks[c.type_id](c.arg_value)}'
	except Exception as e:
		return f'!!failed to render check {c} --- {e}'


instances = {
	3: lambda args, e: f'variable_{args[0]} := {args[1]}',
	6: lambda args, e: f'group_command({args[9]}, command={args[0]}, x={args[1]}, y={args[2]})',
	8: lambda args, e: f'variable_{args[0]}++',
	16: lambda args, e: f'hide_unit({args[0]})',
	17: lambda args, e: f'show_unit({args[0]})',
	18: lambda args, e: f'polymorph_unit({args[0]}, as={args[1]})',
	19: lambda args, e: f'change_unit_owner(unit={args[0]}, new_owner={args[1]})',
	21: lambda args, e: f'cast {spell(e, args[4], args[5])} from ({args[0]}, {args[1]}) to ({args[2]}, {args[3]})',
	22: lambda args, e: f'change_group_owner(group={args[0]}, new_owner={args[1]})',
	25: lambda args, e: f'create_trigger({spell(e, args[0], args[1])}, trigger=({args[2]}, {args[3]}), from=({args[4]}, {args[5]}), to=({args[6]}, {args[7]}))',
	24: lambda args, e: f'cast {spell(e, args[3], args[4])} from ({args[0]}, {args[1]}) to unit {args[2]}',
	27: lambda args, e: f'move_unit({args[0]}, x={args[1]}, y={args[2]})',
	28: lambda args, e: f'give_all(from_unit={args[0]}, to_unit={args[1]})',
	30: lambda args, e: f'cast({spell(e, args[1], 0)}, unit={args[0]}, duration={args[2]})',
	32: lambda args, e: f'hide_group({args[0]})',
	33: lambda args, e: f'show_group({args[0]})',
	34: unit_param_instance,
	38: lambda args, e: f'remove_item_from_everyone({args[0]})',
	65538: lambda args, e: f'start_location(x={args[0]}, y={args[1]})',
}
def render_instance(instance_id, map_info, engine_data):
	c = map_info.instances.get(instance_id)
	if not c:
		return f'(!broken instance {instance_id})'

	try:
		return f'{instances[c.type_id](c.arg_value, engine_data)}'
	except Exception as e:
		return f'!!failed to render instance {c} --- {e}'


def render_triggers(map_info, engine_data, emit):
	check = lambda c: render_check(c, map_info)
	cmps = ['=', '!=', '>', '<', '>=', '<=']

	if map_info.triggers:
		emit('Triggers:')

	for trigger in map_info.triggers:
		once = ' (once)' if trigger.execute_once else ''
		emit(f'  Trigger {trigger.name}{once}:')
		emit(f'    if', end='')

		if trigger.check_ids[0] and trigger.check_ids[1]:
			emit(f' {check(trigger.check_ids[0])} {cmps[trigger.check_operators[0]]} {check(trigger.check_ids[1])}', end='')
		if trigger.check_ids[2] and trigger.check_ids[3]:
			emit(f' AND {check(trigger.check_ids[2])} {cmps[trigger.check_operators[1]]} {check(trigger.check_ids[3])}', end='')
		if trigger.check_ids[4] and trigger.check_ids[5]:
			emit(f' AND {check(trigger.check_ids[4])} {cmps[trigger.check_operators[2]]} {check(trigger.check_ids[5])}', end='')

		emit(f'\n    then ', end='')
		instances = []
		for instance_id in trigger.instance_ids:
			if instance_id:
				instances.append(render_instance(instance_id, map_info, engine_data))
		emit(' AND '.join(instances))


class JsonEncoder(json.JSONEncoder):
	def default(self, o):
		if isinstance(o, a2data.Format):
			return o.__dict__
		return json.JSONEncoder.default(self, o)


format_by_fields = {}
for cls in a2data.Format.__subclasses__():
	fields = ' '.join(sorted(field for field in dir(cls) if not field.startswith('_') and field not in ('as_struct', 'size', 'from_unpacked', 'to_packed')))
	if fields in format_by_fields:
		assert False, f'fields for {format_by_fields[fields]} and {cls} are identical --- {fields}'
	format_by_fields[fields] = cls


def json_decode(d: dict):
	fields = ' '.join(sorted(d.keys()))
	if fields not in format_by_fields:
		return d
	return format_by_fields[fields](**d)


def map_rename(fname, map_info):
	return re.sub(r'[^\w_. -]', '', map_info.info.map_name) + '--' + os.path.basename(fname)


def diplomacy_title(d):
	suffix = '+view' if d & 0x10 else ''
	if d & 0x1:
		return 'enemy' + suffix
	if d & 0x2:
		return 'friend' + suffix
	return 'neutral' + suffix


def process_file(fname, engine_data, args):
	if fname.endswith('.json'):
		with open(fname, 'r') as fin:
			map_info = json.load(fin, object_hook=json_decode)
	else:
		map_info = parser.parse(fname)

	print(f'{fname}: {map_info.info.map_name}', file=sys.stderr)

	if args.save:
		result_file = os.path.join(args.save, os.path.basename(fname))
		if result_file.endswith('.json'):
			result_file = result_file[:-5] + '.alm'
		marshaller.marshal(map_info, result_file)
		return

	if args.output_format == 'json':
		if args.output_directory:
			emit_name = re.sub(r'[^\w_. -]', '', map_info.info.map_name).replace(' ', '_') + '.json'

			with open(os.path.join(args.output_directory, emit_name), 'w') as emit_file:
				json.dump(map_info, emit_file, indent=4, ensure_ascii=False, cls=JsonEncoder)
		else:
			json.dump(map_info, sys.stdout, indent=4, ensure_ascii=False, cls=JsonEncoder)
		return

	emit_name = re.sub(r'[^\w_. -]', '', map_info.info.map_name).replace(' ', '_') + '.txt'

	text = process_file_internal(fname, engine_data, map_info, args)

	if args.output_directory:
		server_types = set([''])
		if args.categorize:
			assert args.output_directory, f'output directory must be specified for categorization'

			clean_name = re.sub('  +', ' ', map_info.info.map_name.replace('"', ''))
			server_types = set()
			for server, maps in args.categorize.items():
				for m in maps:
					if m == clean_name:
						server_types.add(server.rsplit(' ', 1)[0])
			if not server_types:
				assert False, f'{clean_name} is not in the list of maps'
		
		for server_type in server_types:
			d = os.path.join(args.output_directory, server_type.replace(' ', '_').lower())
			if not os.path.exists(d):
				os.makedirs(d)

			with open(os.path.join(d, emit_name), 'w') as emit_file:
				emit_file.write(text)
	else:
		print(text, end='')


def process_file_internal(fname, engine_data, map_info, args):
	res = io.StringIO()
	def emit(*args, **kwargs):
		print(*args, **kwargs, file=res)

	UNIT = 4
	GROUP = 2
	BUILDING = 9
	PLAYER = 3

	interesting = collections.defaultdict(set)

	for check in list(map_info.checks.values()) + list(map_info.instances.values()):
		for arg_type, value in zip(check.arg_type, check.arg_value):
			interesting[arg_type].add(value)

	if args.rename:
		dir_renamed = os.path.join(os.path.dirname(fname), 'renamed')
		new_name = map_rename(fname, map_info)
		renamed = os.path.join(dir_renamed, new_name)
		try:
			os.mkdir(dir_renamed)
		except FileExistsError:
			pass
		print(f'Copying as {renamed}')
		shutil.copyfile(fname, renamed)

	if args.level is not None and map_info.info.map_level != int(args.level):
		return

	groups = {group.group_id: group for group in map_info.groups}
	buildings = {building.building_id: building for building in map_info.buildings}

	emit(f'Notable enemies:')
	for unit in map_info.units:
		bag = []
		if 0 <= unit.bag_id - 1 < len(map_info.bags):
			bag = map_info.bags[unit.bag_id - 1].items

		no_exp = (unit.more_flags & 0x8) != 0
		unit_has_drop = not no_exp and any(not b.wielded for b in bag)
		if args.wields:
			unit_has_drop = len(bag)

		if args.units or unit_has_drop or unit.unit_id in interesting[UNIT] or unit.group_id in interesting[GROUP]:
			extra = ''
			if unit.hp != 65535 or unit.max_hp != 65535:
				extra = f' with {unit.hp}/{unit.max_hp} HP'

			d = map_info.players[0].diplomacy[unit.player_id - 1]
			if d & 0x2:
				extra += ' (ally)'
			elif not d & 0x1:
				extra += ' (neutral)'

			referenced = ''
			if unit.unit_id in interesting[UNIT]:
				referenced = 'unit'
			if unit.group_id in interesting[GROUP]:
				if referenced:
					referenced += '+'
				referenced += 'group'

			if referenced:
				extra += f' {color_reference("referenced " + referenced)}'

			repop_time = 120
			group_flags = 0
			if unit.group_id in groups:
				repop_time = groups[unit.group_id].repop_time
				group_flags = groups[unit.group_id].flags

			no_exp_str = ''
			if no_exp:
				no_exp_str = f', no_exp'

			emit(f'  {engine_data.unit_name(unit.server_id)} unit at x={unit.x}, y={unit.y}: ID={unit.unit_id}, flags={unit.more_flags}{extra}{no_exp_str}, group={unit.group_id} (repop={repop_time}, gflags={group_flags})')

		if unit_has_drop:
			items = {}
			for item in bag:
				if item.wielded and not args.wields:
					continue
				item_str = engine_data.item_names[item.item_id] + ' (%s)'%int(item.item_id)
				if item.effect > 0:
					effect = map_info.effects[item.effect - 1]
					if effect.spell_type_id != 0:
						item_str += ' of ' + spell(engine_data, effect.spell_type_id, effect.spell_power)

					if effect.modifiers:
						# Collapse all modifiers into a sum of them.
						moddict = {}
						for modifier in sorted(effect.modifiers, key=lambda m: m.x):
							moddict[modifier.x] = moddict.get(modifier.x, 0) + modifier.y

						modstr = ''
						for k, v in moddict.items():
							modstr += f' {engine_data.item_modifiers[k]}={v}'
						item_str += f' with {color_modifier(modstr)}'
				items[item_str] = items.get(item_str, 0) + 1

			for item_str, count in items.items():
				drops_or_wields = 'wields' if item.wielded else 'drops'
				if count > 1:
					emit(f'    {drops_or_wields} {color_amount(count)}x {item_str}')
				else:
					emit(f'    {drops_or_wields} {item_str}')

	if interesting[BUILDING]:
		emit(f'Referenced buildings:')
		for building in map_info.buildings:
			if building.building_id in interesting[BUILDING]:
				emit(f'  building: {building}')

	render_triggers(map_info, engine_data, emit)

	emit(f'On-map effects: {len([e for e in map_info.effects if e.x != 0])} total')
	for effect in map_info.effects:
		if effect.x == 0 or effect.y == 0:
			continue

		building_id = effect.max_magic_damage * 256 + effect.min_magic_damage
		flag = effect.magic_type

		effect_str = f'at x={effect.x}, y={effect.y} at range={effect.range}'

		if effect.spell_type_id != 0:
			effect_str += ' ' + spell(engine_data, effect.spell_type_id, effect.spell_power)

		from_ally_building = False

		if building_id:
			if building_id not in buildings:
				effect_str += f' [from missing building {building_id}]'
			else:
				building = buildings[building_id]
				player = map_info.players[building.player-1]
				effect_str += f' [from building {building_id} (x={building.x}, y={building.y}) - {diplomacy_title(player.diplomacy[0])} player {player.name}]'

				if player.diplomacy[0] & 0x2:
					from_ally_building = True

		assert len(effect.modifiers) in [0, 2], f'weird effect.modifiers: {effect.modifiers} on {effect}'

		if effect.modifiers:
			_from, _to = effect.modifiers
			effect_str += f' from ({_from.x}, {_from.y}) to ({_to.x}, {_to.y}) --- {{flags: {_from.flags}, {_to.flags}}}'

		if args.effects or from_ally_building:
			emit(f'  {effect_str}')

	players = set([1]) | interesting[PLAYER]
	if len(players) > 1:
		emit('Interesting players:')
		for player_id in players:
			p = map_info.players[player_id - 1]
			emit(f'  {p.name}, id={player_id}  [[ {p} ]]: ', end='')
			for other_id in players:
				if player_id == other_id:
					continue

				d = p.diplomacy[other_id - 1]
				t = diplomacy_title(d)

				emit(f'{t} to {map_info.players[other_id - 1].name}, ', end='')
			emit()

	return res.getvalue()


def parse_categorization(fname):
	with open(fname, 'rt') as f:
		lines = f.readlines()

	maps = {}
	server = ''
	map_list = []

	for line in lines:
		if not line:
			continue
		parts = line.split('\t')

		if parts[0]:
			if server:
				maps[server] = map_list
			server = parts[0].split(' Цикл')[0].split(']')[1].strip()
			map_list = []
		else:
			map_list.append(parts[1])

	maps[server] = map_list
	return maps


def main():
	arg_parser = argparse.ArgumentParser(prog='alm_parser')
	arg_parser.add_argument('filename', nargs='*')
	arg_parser.add_argument('-d', '--allods_data_directory')
	arg_parser.add_argument('-r', '--rename', action='store_true')
	arg_parser.add_argument('-u', '--units', action='store_true')
	arg_parser.add_argument('-e', '--effects', action='store_true')
	arg_parser.add_argument('-w', '--wields', action='store_true')
	arg_parser.add_argument('-l', '--level')
	arg_parser.add_argument('-m', '--monsters')
	arg_parser.add_argument('--drops_potions', type=int)
	arg_parser.add_argument('--has_magic', type=int)
	arg_parser.add_argument('--output_directory', default=None)
	arg_parser.add_argument('--categorize')
	arg_parser.add_argument('--output_format', default='text', choices=['text', 'json'])
	arg_parser.add_argument('-s', '--save')
	args = arg_parser.parse_args()

	engine_data = parser.parse_engine_data(args.allods_data_directory, args.filename)

	if args.monsters:
		select_units = [unit for unit in engine_data.unit_kinds.values() if args.monsters in unit.name]
		assert select_units

		for k, v in select_units[0].__dict__.items():
			if isinstance(v, int) or isinstance(v, str) or (isinstance(v, list) and v and isinstance(v[0], int)):
				a = "".join(f'{str(getattr(g, k)):25}' for g in select_units)
				print(f'{k:25}: {a}')

		print()
		for unit in select_units:
			if unit.items:
				nl = '\n  '
				print(f'{unit.name} items: {nl}{nl.join(unit.items)}')
		return

	if args.drops_potions:
		for unit in engine_data.unit_kinds.values():
			if unit.kingdom == 62 and unit.drop_mask & 0x4000000 and unit.drop_price_min < unit.drop_price_max:
				if args.drops == -1 or unit.drop_price_min <= args.drops <= unit.drop_price_max:
					print(f'Unit {unit.name} can drop books/potions. Range: {unit.drop_price_min}--{unit.drop_price_max}')
		return

	if args.has_magic:
		units = []
		for unit in engine_data.unit_kinds.values():
			if unit.known_spells != 4294967295 and unit.known_spells & (1 << args.has_magic):
				units.append(unit.name)
			elif unit.kingdom == 62 and args.has_magic in (unit.spell_1, unit.spell_2, unit.spell_3):
				units.append(unit.name + ' (ability)')

		print(f'Mobs that know {spell(engine_data, args.has_magic, 0)}: {", ".join(units)}')
		return

	if args.categorize:
		args.categorize = parse_categorization(args.categorize)
		if not args.output_directory:
			print(f'output directory must be specified for categorization')
			return

	for f in args.filename:
		process_file(f, engine_data, args)


if __name__ == '__main__':
	main()
