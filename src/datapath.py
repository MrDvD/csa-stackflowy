from enum import Enum
from typing import List, Tuple

class MuxTdSel(Enum):
  DATA_READ = 0
  S_SHIFT = 1
  ALU_RESULT = 2
  NIR = 3

class MuxSSel(Enum):
  STACK_PREV = 0
  TD_SHIFT = 1

class MuxAluLeftSel(Enum):
  S = 0
  ZERO = 1

class MuxAluRightSel(Enum):
  TD = 0
  SR = 1

class MuxDataReadSel(Enum):
  RAM = 0
  IO = 1

class MuxSrSel(Enum):
  ALU_RESULT = 0
  ALU_FLAGS = 1

class AluOp(Enum):
  ADD = 0
  SUB = 1
  AND = 2
  OR = 3
  PASSTHROUGH_L = 4
  PASSTHROUGH_R = 5

class DataPath:
  def __init__(self, mem_size: int, input_data: List[int]):
    self.memory: List[int] = [0] * mem_size
    self.data_stack: List[int] = list()
    self.input_buffer: List[int] = input_data
    self.output_buffer: List[int] = list()
    self.s: int = 0
    self.td: int = 0
    self.sr_v: bool = False
    self.sr_c: bool = False

  def _read_data_mux(self, sel: MuxDataReadSel) -> int:
    if sel == MuxDataReadSel.RAM:
      if 0 <= self.td < len(self.memory):
        return self.memory[self.td]
      return 0
    elif sel == MuxDataReadSel.IO:
      if self.input_buffer:
        return self.input_buffer.pop(0)
      return 0
    return 0

  def _execute_alu(self, op: AluOp, left: int, right: int) -> Tuple[int, bool, bool]:
    left = left & 0xFFFFFFFF
    right = right & 0xFFFFFFFF
    res: int = 0
    v: bool = False
    c: bool = False

    if op == AluOp.ADD:
      res = left + right
      c = res > 0xFFFFFFFF
      v = (not (left & 0x80000000) and not (right & 0x80000000) and bool(res & 0x80000000)) or \
          (bool(left & 0x80000000) and bool(right & 0x80000000) and not (res & 0x80000000))
    elif op == AluOp.SUB:
      res = left - right
      c = left < right
      v = (not (left & 0x80000000) and bool(right & 0x80000000) and bool(res & 0x80000000)) or \
          (bool(left & 0x80000000) and not (right & 0x80000000) and not (res & 0x80000000))
    elif op == AluOp.AND:
      res = left & right
    elif op == AluOp.OR:
      res = left | right
    elif op == AluOp.PASSTHROUGH_L:
      res = left
    elif op == AluOp.PASSTHROUGH_R:
      res = right

    return res & 0xFFFFFFFF, v, c

  def latch_td(self, sel: MuxTdSel, dr_sel: MuxDataReadSel = MuxDataReadSel.RAM, alu_op: AluOp = AluOp.PASSTHROUGH_L, ifetch_val: int = 0) -> None:
    left_mux: int = self.s if False else 0
    right_mux: int = self.td if False else 0
    alu_res, _, _ = self._execute_alu(alu_op, left_mux, right_mux)

    if sel == MuxTdSel.DATA_READ:
      self.td = self._read_data_mux(dr_sel)
    elif sel == MuxTdSel.S_SHIFT:
      self.td = self.s
    elif sel == MuxTdSel.ALU_RESULT:
      self.td = alu_res
    elif sel == MuxTdSel.NIR:
      self.td = ifetch_val & 0xFFFFFFFF

  def latch_s(self, sel: MuxSSel) -> None:
    if sel == MuxSSel.STACK_PREV:
      if self.data_stack:
        self.s = self.data_stack.pop()
      else:
        self.s = 0
    elif sel == MuxSSel.TD_SHIFT:
      self.s = self.td

  def latch_sr(self, sel: MuxSrSel, alu_op: AluOp = AluOp.PASSTHROUGH_L, alu_l_sel: MuxAluLeftSel = MuxAluLeftSel.S, alu_r_sel: MuxAluRightSel = MuxAluRightSel.TD) -> None:
    left: int = self.s if alu_l_sel == MuxAluLeftSel.S else 0
    right: int = 0
    if alu_r_sel == MuxAluRightSel.TD:
      right = self.td
    elif alu_r_sel == MuxAluRightSel.SR:
      right = (1 if self.sr_v else 0) | (2 if self.sr_c else 0)

    alu_res, v, c = self._execute_alu(alu_op, left, right)

    if sel == MuxSrSel.ALU_RESULT:
      self.sr_v = bool(alu_res & 1)
      self.sr_c = bool(alu_res & 2)
    elif sel == MuxSrSel.ALU_FLAGS:
      self.sr_v = v
      self.sr_c = c

  def stack_push(self) -> None:
    self.data_stack.append(self.s)

  def write_memory(self) -> None:
    if 0 <= self.td < len(self.memory):
      self.memory[self.td] = self.s

  def write_io(self) -> None:
    self.output_buffer.append(self.s)