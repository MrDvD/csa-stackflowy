import os, sys, re, struct
from typing import List
from isa import Opcode, Label, Segment, ArgType, String, Numeral
from preprocessor import Preprocessor
from dataclasses import dataclass

@dataclass
class Instruction:
  opcode: Opcode
  arg: str | None = None

@dataclass
class DataSegment:
  start: int | None
  data: bytearray

@dataclass
class InstructionsSegment:
  start: int | None
  data: List[Instruction]

class Translator:
  def __init__(self):
    self.two_left_args = re.compile(r'\(\s*([A-Za-z]\w*),\s*([A-Za-z]\w*)\s*:')
    self.one_left_arg = re.compile(r'\(\s*([A-Za-z]\w*)\s*:')
    self.no_left_args = re.compile(r'\(\s*:')
    self.two_right_args = re.compile(r'(\w+)\s*(,|\+|-|==|>=?|<=?|\+\*|\+\/|&|\||\^)\s*(\w+)\s*\)')
    self.one_right_arg = re.compile(r'(-|~|<<|>>)?\s*(\w+)\s*\)')
    self.no_right_args = re.compile(r'\)')
    self.effect = re.compile(r'(=>|<=)\s*(MEM_DATA|IN|OUT|FLG|RET|\.|\?)?')
    
  def _translate_data(self, address: int, data_str: str) -> DataSegment:
    content: bytearray = bytearray()
    for line in data_str.strip().splitlines():
      idx: int = 0
      line = line.strip()
      while idx < len(line):
        s = String.regex.match(line, idx)
        n = Numeral.regex.match(line, idx)
        if s:
          content.extend(struct.pack("<c", list(s.group(1))))
          continue
        if n:
          content.extend(struct.pack("i", list(n.group(0))))
          continue
        raise Exception('Unknown data token')
    return DataSegment(address, content)
  
  def _calc_left_space(self, line: str, offset: int = 0) -> int:
    new_line = line[offset:]
    return len(new_line) - len(new_line.lstrip())
  
  def _parse_address(self, raw_address: str | None) -> int | None:
    if raw_address is None:
      return None
    
    match ArgType.get(raw_address):
      case ArgType.HEX:
        return int(raw_address, 16)
      case ArgType.DEC:
        return int(raw_address)
      case _:
        raise Exception(f'Unexpected address: {raw_address}')

  def _translate_instructions(self, address: int | None, instr_str: str) -> InstructionsSegment:
    instructions: List[Instruction] = list()
    for line in instr_str.strip().splitlines():
      idx: int = 0
      line = line.strip()
      if not line:
        continue
      while idx < len(line):
        idx += self._calc_left_space(line[idx:])
        two_l_args = self.two_left_args.match(line, idx)
        one_l_arg = self.one_left_arg.match(line, idx)
        no_l_args = self.no_left_args.match(line, idx)
        effect = self.effect.match(line, idx)
        if two_l_args:
          larg1, larg2 = two_l_args.group(1), two_l_args.group(2)
          idx += self._calc_left_space(line[idx:], offset=len(two_l_args.group(0)))
          two_r_args = self.two_right_args.match(line, idx)
          no_r_args = self.no_right_args.match(line, idx)
          if two_r_args:
            idx += self._calc_left_space(line[idx:], len(two_r_args.group(0)))
            rarg1, op, rarg2 = two_r_args.group(1), two_r_args.group(2), two_r_args.group(3)
            match op:
              case ',':
                if larg1 == rarg2 and larg2 == rarg1:
                  instructions.append(Instruction(Opcode.SWAP))
                  continue
              case '+':
                if larg1 == rarg1 and larg2 == rarg2 or larg1 == rarg2 and larg2 == rarg1:
                  instructions.append(Instruction(Opcode.ADD))
                  continue
              case '-':
                if larg1 == rarg1 and larg2 == rarg2 or larg1 == rarg2 and larg2 == rarg1:
                  instructions.append(Instruction(Opcode.SUB))
                  continue
              case '+*':
                if larg1 == rarg1 and larg2 == rarg2 or larg1 == rarg2 and larg2 == rarg1:
                  instructions.append(Instruction(Opcode.SMUL))
                  continue
              case '+/':
                if larg1 == rarg1 and larg2 == rarg2:
                  instructions.append(Instruction(Opcode.SDIV))
                  continue
              case '&':
                if larg1 == rarg1 and larg2 == rarg2 or larg1 == rarg2 and larg2 == rarg1:
                  instructions.append(Instruction(Opcode.AND))
                  continue
              case '|':
                if larg1 == rarg1 and larg2 == rarg2 or larg1 == rarg2 and larg2 == rarg1:
                  instructions.append(Instruction(Opcode.OR))
                  continue
              case '^':
                if larg1 == rarg1 and larg2 == rarg2 or larg1 == rarg2 and larg2 == rarg1:
                  instructions.append(Instruction(Opcode.XOR))
                  continue
              case '==':
                if larg1 == rarg1 and larg2 == rarg2 or larg1 == rarg2 and larg2 == rarg1:
                  instructions.append(Instruction(Opcode.EQ))
                  continue
              case '>':
                if larg1 == rarg1 and larg2 == rarg2 or larg1 == rarg2 and larg2 == rarg1:
                  instructions.append(Instruction(Opcode.GT))
                  continue
              case '<':
                if larg1 == rarg1 and larg2 == rarg2 or larg1 == rarg2 and larg2 == rarg1:
                  instructions.append(Instruction(Opcode.LT))
                  continue
              case '>=':
                if larg1 == rarg1 and larg2 == rarg2 or larg1 == rarg2 and larg2 == rarg1:
                  instructions.append(Instruction(Opcode.GEQ))
                  continue
              case '<=':
                if larg1 == rarg1 and larg2 == rarg2 or larg1 == rarg2 and larg2 == rarg1:
                  instructions.append(Instruction(Opcode.LEQ))
                  continue
              case _:
                raise Exception("Unexpected operator on the right")
          elif no_r_args:
            idx += self._calc_left_space(line[idx:], len(no_r_args.group(0)))
            effect = self.effect.match(line, idx)
            if not effect:
              raise Exception("Unexpected operands sequence")
            arrow, op = effect.group(1), effect.group(2)
            if arrow != "=>":
              raise Exception("Unexpected arrow direction")
            match op:
              case "MEM_DATA":
                instructions.append(Instruction(Opcode.STORE))
                continue
              case "OUT":
                instructions.append(Instruction(Opcode.OUT))
                continue
              case _:
                raise Exception("Unexpected operator on the right")
          else:
            raise Exception("Unsupported operands sequence")
        elif one_l_arg:
          idx += self._calc_left_space(line[idx:], len(one_l_arg.group(0)))
          larg = one_l_arg.group(1)
          two_r_args = self.two_right_args.match(line, idx)
          one_r_arg = self.one_right_arg.match(line, idx)
          no_r_args = self.no_right_args.match(line, idx)
          if two_r_args:
            idx += self._calc_left_space(line[idx:], len(two_r_args.group(0)))
            rarg1, op, rarg2 = two_r_args.group(1), two_r_args.group(2), two_r_args.group(3)
            match op:
              case ',':
                if larg == rarg1 and larg == rarg2:
                  instructions.append(Instruction(Opcode.DUP))
                  continue
              case _:
                raise Exception("Unexpected operator on the right")
          elif one_r_arg:
            idx += self._calc_left_space(line[idx:], len(one_r_arg.group(0)))
            op, rarg = one_r_arg.group(1), one_r_arg.group(2)
            if op:
              if larg != rarg:
                raise Exception("Argument mismatch")
              match op:
                case '~':
                  instructions.append(Instruction(Opcode.INV))
                  continue
                case '-':
                  instructions.append(Instruction(Opcode.NEG))
                  continue
                case '<<':
                  instructions.append(Instruction(Opcode.SHLT))
                  continue
                case '>>':
                  instructions.append(Instruction(Opcode.SHRT))
                  continue
                case _:
                  raise Exception("Unknown unary operator")
            if larg == rarg:
              raise Exception("Argument duplication")
            effect = self.effect.match(line, idx)
            if not effect:
              raise Exception("Unknown operands sequence")
            arrow, op = effect.group(1), effect.group(2)
            if arrow != '<=':
              raise Exception("Unexpected arrow direction")
            match op:
              case 'MEM_DATA':
                instructions.append(Instruction(Opcode.LOAD))
                continue
              case 'IN':
                instructions.append(Instruction(Opcode.IN))
                continue
              case _:
                raise Exception("Unexpected effect on the right")
          elif no_r_args:
            idx += self._calc_left_space(line[idx:], len(no_r_args.group(0)))
            effect = self.effect.match(line, idx)
            if not effect:
              instructions.append(Instruction(Opcode.POP))
              continue
            arrow, op = effect.group(1), effect.group(2)
            if arrow != '=>':
              raise Exception('Unexpected arrow direction')
            if op != 'FLG':
              raise Exception('Unexpected effect on the right')
            instructions.append(Instruction(Opcode.SFLG))
            continue
          else:
            raise Exception("Unsupported operands sequence")
        elif no_l_args:
          idx += self._calc_left_space(line[idx:], len(no_l_args.group(0)))
          one_r_arg = self.one_right_arg.match(line, idx)
          no_r_args = self.no_right_args.match(line, idx)
          if one_r_arg:
            idx += self._calc_left_space(line[idx:], len(one_r_arg.group(0)))
            op, rarg = one_r_arg.group(1), one_r_arg.group(2)
            if op:
              raise Exception('Unexpected unary operator')
            effect = self.effect.match(line, idx)
            if not effect:
              instructions.append(Instruction(Opcode.PUSH, arg=rarg))
              continue
            arrow, op = effect.group(1), effect.group(2)
            if arrow != '<=':
              raise Exception('Unexpected arrow direction')
            if op != 'FLG':
              raise Exception('Unexpected effect on the right')
            instructions.append(Instruction(Opcode.LFLG))
            continue
          elif no_r_args:
            idx += self._calc_left_space(line[idx:], len(no_r_args.group(0)))
            instructions.append(Instruction(Opcode.NOP))
            continue
          else:
            raise Exception("Unsupported operands sequence")
        elif effect:
          idx += self._calc_left_space(line[idx:], len(effect.group(0)))
          arrow, op = effect.group(1), effect.group(2)
          if arrow != '=>':
            raise Exception('Unexpected arrow direction')
          if not op:
            label_match = Label.regex.match(line, idx)
            if not label_match:
              raise Exception("Label name expected but not found")
            label = label_match.group(0)
            idx += self._calc_left_space(line[idx:], len(label))
            instructions.append(Instruction(Opcode.JMP, arg=label))
          match op:
            case 'HLT':
              instructions.append(Instruction(Opcode.HLT))
              continue
            case '?':
              label_match = Label.regex.match(line, idx)
              if not label_match:
                raise Exception("Label name expected but not found")
              label = label_match.group(0)
              idx += self._calc_left_space(line[idx:], len(label))
              instructions.append(Instruction(Opcode.JMPIF, arg=label))
              continue
            case 'RET':
              instructions.append(Instruction(Opcode.RET))
              continue
            case '.':
              label_match = Label.regex.match(line, idx)
              if not label_match:
                raise Exception("Label name expected but not found")
              label = label_match.group(0)
              idx += self._calc_left_space(line[idx:], len(label))
              instructions.append(Instruction(Opcode.CALL, arg=label))
              continue
            case _:
              raise Exception('Unexpected effect on the right')
        else:
          raise Exception("Unknown tokens found")

    return InstructionsSegment(address, instructions)

  def _find_next(self, code: str, start: int) -> int:
    d = Segment.data_regex.search(code, start)
    t = Segment.text_regex.search(code, start)
    matches = [m.start() for m in [d, t] if m]
    return min(matches) if matches else len(code)
  
  def _align_segments(self, segments: List[DataSegment | InstructionsSegment]) -> bytes:
    # check for lack of overlaps
    # then generate bytes sequence
    ...

  def translate(self, code: str) -> bytes:
    idx = 0
    segments: List[DataSegment | InstructionsSegment] = list()
    while idx < len(code):
      d_match = Segment.data_regex.match(code, idx)
      i_match = Segment.text_regex.match(code, idx)
      if d_match:
        raw_addr = d_match.group(1)
        addr = self._parse_address(raw_addr)
        content_start = idx + d_match.end()
        content_end = self._find_next(code, content_start)
        data_segment = self._translate_data(addr, code[content_start:content_end])
        segments.append(data_segment)
        idx = content_end
      elif i_match:
        raw_addr = i_match.group(1)
        addr = self._parse_address(raw_addr)
        content_start = idx + i_match.end()
        content_end = self._find_next(code, content_start)
        text_segment = self._translate_instructions(addr, code[content_start:content_end])
        segments.append(text_segment)
        idx = content_end
      elif code[idx].isspace():
        idx += 1
      else:
        raise Exception(f"Unknown segment at index {idx}: {code[idx:idx+15]!r}")
    return self._align_segments(segments)

if __name__ == "__main__":
  assert len(sys.argv) == 3, "Wrong arguments: translator.py <input_file> <target_file>"
  _, source, target = sys.argv
  translator, preprocessor = Translator(), Preprocessor()

  with open(source, encoding="utf-8") as f:
    source = f.read()

  code = preprocessor.preprocess(source)
  bin_code = translator.translate(code)

  os.makedirs(os.path.dirname(os.path.abspath(target)) or ".", exist_ok=True)
  with open(target, "wb") as f:
    f.write(bin_code)
  with open(target + ".hex", "w") as f:
    f.write(bin_code.hex())

  print("source LoC:", len(source.split("\n")), "code instr:", len(code))