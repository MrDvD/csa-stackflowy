class CacheMemory:
  def __init__(self, size):
    self.memory = [0] * size
    self.cached_lines = set()

  def read_byte(self, address):
    line = address // 4
    if line in self.cached_lines:
      return self.memory[address], 1, True
    self.cached_lines.add(line)
    return self.memory[address], 10, False

  def write_byte(self, address, value):
    self.memory[address] = value & 0xFF
    line = address // 4
    self.cached_lines.add(line)
    return 1