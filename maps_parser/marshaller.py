import io
import struct

import a2data


header_size = a2data.SectionHeader.size()


class Marshaller():
	def __init__(self, allods_map: a2data.AllodsMap):
		self.buffer = io.BytesIO()
		self.map = allods_map

	def _write(self, value: a2data.Format):
		fmt_str = value.__class__.as_struct()
		packed = value.to_packed(value)
		content = struct.pack(fmt_str, *packed)
		self.buffer.write(content)

	def _section_header(self, id, section_size):
		return a2data.SectionHeader(
			seven_or_five = 7,
			alm_size = 20,
			section_size = section_size,
			id = id,
			signature = 0xBEEFBEEF,
		)

	def marshal(self) -> bytes:
		self._write(a2data.Header(
			signature = a2data.alm_signature,
			alm_size = 20,
			something_0 = 0,
			num_sections = 13,
			version = a2data.alm_version,
		))

		self._section(0, self._info_section)
		self._section(1, self._landscape_section)
		self._section(2, self._heights_section)
		self._section(3, self._objects_section)
		self._section(5, self._players_section)
		self._section(11, self._shops_section)
		self._section(4, self._bridges_section)
		self._section(9, self._effects_section)
		self._section(8, self._bags_section)
		self._section(6, self._units_section)
		self._section(7, self._logics_section)
		self._section(10, self._groups_section)
		self._section(12, self._music_section)

		return self.buffer.getvalue()
	
	def _section(self, id, wrapped_implementation):
		start = self.buffer.tell()
		self._write(self._section_header(id, 0))

		wrapped_implementation()

		end = self.buffer.tell()
		self.buffer.seek(start)
		self._write(self._section_header(id, end - start - header_size))
		self.buffer.seek(end)
		assert self.buffer.tell() == end

	def _info_section(self):
		self.map.info.num_players = len(self.map.players)
		self.map.info.num_buildings = len(self.map.buildings)
		self.map.info.num_units = len(self.map.units)
		self.map.info.num_logic = len(self.map.instances) + len(self.map.checks) + len(self.map.triggers)
		self.map.info.num_bags = len(self.map.bags)
		self.map.info.num_groups = len(self.map.groups)
		self.map.info.num_inns = len(self.map.inns)
		self.map.info.num_shops = len(self.map.shops)
		self.map.info.num_signs = len(self.map.signs)
		self.map.info.num_music = len(self.map.music) - 1
		
		self._write(self.map.info)

	def _landscape_section(self):
		for t in self.map.tiles:
			self._write(a2data.Landscape(tile=t))

	def _heights_section(self):
		for h in self.map.heights:
			self._write(a2data.Height(height=h))

	def _objects_section(self):
		for o in self.map.objects:
			self._write(a2data.Object(object_id=o))

	def _bridges_section(self):
		for building in self.map.buildings:
			self._write(building)

			if building.type_id >= 0x1000000:
				self._write(a2data.BridgeSize(bridge_width=building.bridge_width, bridge_height=building.bridge_height))

	def _players_section(self):
		for p in self.map.players:
			self._write(p)

	def _units_section(self):
		for u in self.map.units:
			self._write(u)

	def _logics_section(self):
		self._write(a2data.Instances(num_instances=len(self.map.instances)))
		for i in sorted(self.map.instances.values(), key=lambda inst: inst.index):
			self._write(i)

		self._write(a2data.Instances(num_instances=len(self.map.checks)))
		for c in sorted(self.map.checks.values(), key=lambda check: check.index):
			self._write(c)

		self._write(a2data.Instances(num_instances=len(self.map.triggers)))
		for t in self.map.triggers:
			self._write(t)

	def _bags_section(self):
		for bag in self.map.bags:
			bag.num_items = len(bag.items)
			self._write(bag)
			for item in bag.items:
				self._write(item)

	def _effects_section(self):
		self._write(a2data.Effects(num_effects=len(self.map.effects)))
		for effect in self.map.effects:
			effect.num_modifiers = len(effect.modifiers)
			self._write(effect)
			for mod in effect.modifiers:
				self._write(mod)

	def _groups_section(self):
		for g in self.map.groups:
			self._write(g)

	def _shops_section(self):
		for i in self.map.inns:
			self._write(i)
		for s in self.map.shops:
			self._write(s)
		for s in self.map.signs:
			self._write(s)

	def _music_section(self):
		for m in self.map.music:
			self._write(m)


def marshal(allods_map: a2data.AllodsMap, filename: str):
	with open(filename, 'wb') as outf:
		outf.write(Marshaller(allods_map).marshal())
