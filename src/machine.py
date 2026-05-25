from datapath import DataPath
from controlunit import ControlUnit
from typing import List
import logging
import sys

class Processor:
  def __init__(self, data_memory_size: int, text_memory_size: int, input_data: List[int]):
    self.data_path: DataPath = DataPath(data_memory_size, input_data)
    self.control_unit: ControlUnit = ControlUnit(text_memory_size, list(), dict())

  def load_text(self, text_code: bytes) -> None:
    for idx, byte in enumerate(text_code):
      self.control_unit.rom_instructions[idx] = byte

  def load_data(self, data_code: bytes) -> None:
    for idx, byte in enumerate(data_code):
      self.data_path.memory[idx] = byte

  def run(self, limit: int) -> tuple[str, int]:
    logging.debug("%s", self.control_unit)
    try:
      while self.control_unit.model_tick < limit and not self.control_unit.halted:
        self.control_unit.tick()
        logging.debug("%s", self.control_unit)
    except EOFError:
      logging.warning("Input buffer is empty!")
    except StopIteration:
      pass

    if self.control_unit.model_tick >= limit:
      logging.warning("Limit exceeded!")

    output: str = "".join(map(str, self.data_path.output_buffer))
    logging.info("output_buffer: %s", repr(output))
    return output, self.control_unit.model_tick

def main(data_file: str, text_file: str, input_file: str, data_mem_size: int, limit: int) -> None:
  with open(text_file, "rb") as file:
    text_code: bytes = file.read()

  with open(data_file, "rb") as file:
    data_code: bytes = file.read()

  with open(input_file, encoding="ascii") as file:
    input_text: str = file.read()
    input_data: list[int] = [ord(char) for char in input_text]

  processor: Processor = Processor(data_memory_size=int(data_mem_size), text_memory_size=len(text_code), input_data=input_data)
  processor.load_text(text_code)
  processor.load_data(data_code)

  output, ticks = processor.run(limit)

  print("".join(output))
  print("ticks:", ticks)

if __name__ == "__main__":
  logging.getLogger().setLevel(logging.DEBUG)
  assert len(sys.argv) == 6, "Wrong arguments: machine.py <data_file> <text_file> <input_file> <data_mem_size> <limit>"
  _, data_file_arg, text_file_arg, input_file_arg, data_mem_size, limit = sys.argv
  assert data_mem_size.isdecimal(), "Wrong arguments: <data_mem_size> is not a decimal number"
  assert limit.isdecimal(), "Wrong arguments: <limit> is not a decimal number"
  main(data_file_arg, text_file_arg, input_file_arg, int(data_mem_size), int(limit))