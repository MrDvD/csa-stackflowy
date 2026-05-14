from enum import Enum, IntEnum
import re

class Opcode(Enum):
  PUSH = (0x0, "push")
  POP  = (0x1, "pop")
  DUP  = (0x2, "duplicate")
  SWAP = (0x3, "swap")

  ADD  = (0x4, "add")
  SUB  = (0x5, "substract")
  SMUL = (0x6, "multiply_step")
  SDIV = (0x7, "divide_step")
  AND  = (0x8, "and")
  OR   = (0x9, "or")
  XOR  = (0xA, "xor")
  SHLT = (0xB, "shift_left")
  SHRT = (0xC, "shift_right")
  INV  = (0xD, "invert")
  NEG  = (0xE, "negative")

  EQ   = (0xF, "is_==")
  GT   = (0x10, "is_>")
  LT   = (0x11, "is_<")
  GEQ  = (0x12, "is_>=")
  LEQ  = (0x13, "is_<=")

  JMP   = (0x14, "jump")
  JMPIF = (0x15, "jump_if")

  CALL = (0x16, "call")
  RET  = (0x17, "ret")

  LFLG = (0x18, "load_flags")
  SFLG = (0x19, "store_flags")

  LOAD  = (0x1A, "load")
  STORE = (0x1B, "store")
  IN    = (0x1C, "in")
  OUT   = (0x1D, "out")

  HLT = (0x1E, "halt")
  NOP = (0x1F, "no_operation")

  def __init__(self, value: int, mnemonic: str):
    self._value_ = value
    self.mnemonic = mnemonic

  def __str__(self):
    return self.mnemonic

class ArgType(IntEnum):
  DEC = 0
  HEX = 1
  LABEL = 2
  UNKNOWN = 3

  @staticmethod
  def get(raw_arg: str) -> 'ArgType':
    if re.match(r'^0x\d+$', raw_arg):
      return ArgType.HEX
    if re.match(r'^_\w+$', raw_arg):
      return ArgType.LABEL
    if re.match(r'^\d+$', raw_arg):
      return ArgType.DEC
    return ArgType.UNKNOWN

class Label:
  pattern = r'_\w+'
  regex = re.compile(pattern)

class String:
  pattern = r'\"(.+)\"'
  regex = re.compile(pattern)

class Numeral:
  pattern = r'0x\d+|-?\d+'
  regex = re.compile(pattern)

class Variable:
  pattern = r'[A-Za-z]\w*'
  regex = re.compile(pattern)

class Comment:
  pattern = r';.*'
  regex = re.compile(pattern)

class Macros:
  if_regex = re.compile(
    r'@if\s*\((.*?)\)\s*\{(.*?)\}'
    r'(?:\s*@elif\s*\((.*?)\)\s*\{(.*?)\})*'
    r'(?:\s*@else\s*\{(.*?)\})?',
    re.DOTALL
  )
  macro_regex = re.compile(
    r'@macro\s+(\w+)\s*\((.*?)\)\s*\{(.*?)\}',
    re.DOTALL
  )
  def_regex = re.compile(r'@define\s+(\w+)\s+(.+)')

class Segment:
  data_regex = re.compile(r'\.data(?:@(0x\d+|\d+))?')
  text_regex = re.compile(r'\.text(?:@(0x\d+|\d+))?')