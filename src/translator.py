import os
import sys
import re
import struct
from typing import List, Dict, Tuple
from isa import Opcode, Label, Segment, ArgType, String, Numeral, Variable, Decoder
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


@dataclass
class LabelDeclaration:
    segment_idx: int
    offset: int
    abs_addr: int | None = None


class Translator:
    def __init__(self):
        self.two_left_args = re.compile(
            rf"\(\s*({Variable.pattern}),\s*({Variable.pattern})\s*:"
        )
        self.one_left_arg = re.compile(rf"\(\s*({Variable.pattern})\s*:")
        self.no_left_args = re.compile(r"\(\s*:")
        self.two_right_args = re.compile(
            rf"({Variable.pattern})\s*(,|\+|-|==|>=?|<=?|\+\*|\+\/|&|\||\^)\s*({Variable.pattern})\s*\)"
        )
        self.one_right_arg = re.compile(
            rf"(-|~|<<|>>)?\s*({Variable.pattern}|{Numeral.pattern}|{Label.pattern})\s*\)"
        )
        self.no_right_args = re.compile(r"\)")
        self.effect = re.compile(r"(=>|<=)\s*(MEM_DATA|IN|OUT|FLG|\.|\?)?")
        self.label_set = re.compile(rf"({Label.pattern}):")
        self.control_flow = re.compile(r"<([^>]+)>")

    def _translate_data(
        self,
        segment_idx: int,
        address: int | None,
        data_str: str,
        labels: Dict[str, LabelDeclaration],
    ) -> DataSegment:
        content: bytearray = bytearray()
        pc: int = -1
        for line in data_str.strip().splitlines():
            idx: int = 0
            line = line.strip()
            while idx < len(line):
                pc += 1
                s = String.regex.match(line, idx)
                n = Numeral.regex.match(line, idx)
                la = self.label_set.match(line, idx)
                if la:
                    label = la.group(1)
                    idx += self._calc_left_space(line[idx:], offset=len(la.group(0)))
                    if label in labels:
                        raise Exception(f"Label duplication: {label}")
                    labels[label] = LabelDeclaration(segment_idx, pc)
                    pc -= 1
                elif s:
                    st = s.group(1)
                    idx += self._calc_left_space(line[idx:], offset=len(s.group(0)))
                    st_bytes = st.encode("ascii")
                    for i in range(0, len(st_bytes), 4):
                        chunk = st_bytes[i : i + 4]
                        padded = chunk.ljust(4, b"\x00")
                        content.extend(
                            struct.pack("<I", struct.unpack(">I", padded)[0])
                        )
                    pc += ((len(st_bytes) + 3) // 4) * 4
                elif n:
                    idx += self._calc_left_space(line[idx:], offset=len(n.group(0)))
                    content.extend(struct.pack("i", list(n.group(0))))
                else:
                    raise Exception("Unknown data token")
        return DataSegment(address, content)

    def _calc_left_space(self, line: str, offset: int = 0) -> int:
        new_line = line[offset:]
        return len(new_line) - len(new_line.lstrip()) + offset

    def _parse_address(self, raw_address: str | None) -> int | None:
        if raw_address is None:
            return None

        match ArgType.get(raw_address):
            case ArgType.HEX:
                return int(raw_address, 16)
            case ArgType.DEC:
                return int(raw_address)
            case _:
                raise Exception(f"Unexpected address: {raw_address}")

    def _translate_instructions(
        self,
        segment_idx: int,
        address: int | None,
        instr_str: str,
        labels: Dict[str, LabelDeclaration],
    ) -> InstructionsSegment:
        instructions: List[Instruction] = list()
        pc = -1

        for line in instr_str.strip().splitlines():
            idx = 0
            line = line.strip()
            if not line:
                continue
            while idx < len(line):
                pc += 1
                idx += self._calc_left_space(line[idx:])
                two_l_args = self.two_left_args.match(line, idx)
                one_l_arg = self.one_left_arg.match(line, idx)
                no_l_args = self.no_left_args.match(line, idx)
                label_set = self.label_set.match(line, idx)
                control_flow_match = self.control_flow.match(line, idx)

                if label_set:
                    label = label_set.group(1)
                    idx += self._calc_left_space(
                        line[idx:], offset=len(label_set.group(0))
                    )
                    if label in labels:
                        raise Exception(f"Label duplication: {label}")
                    labels[label] = LabelDeclaration(segment_idx, pc)
                    pc -= 1
                    continue
                elif two_l_args:
                    larg1, larg2 = two_l_args.group(1), two_l_args.group(2)
                    idx += self._calc_left_space(
                        line[idx:], offset=len(two_l_args.group(0))
                    )
                    two_r_args = self.two_right_args.match(line, idx)
                    no_r_args = self.no_right_args.match(line, idx)
                    if two_r_args:
                        idx += self._calc_left_space(
                            line[idx:], len(two_r_args.group(0))
                        )
                        rarg1, op, rarg2 = (
                            two_r_args.group(1),
                            two_r_args.group(2),
                            two_r_args.group(3),
                        )
                        match op:
                            case ",":
                                if larg1 == rarg2 and larg2 == rarg1:
                                    instructions.append(Instruction(Opcode.SWAP))
                                    continue
                            case "+":
                                if (
                                    larg1 == rarg1
                                    and larg2 == rarg2
                                    or larg1 == rarg2
                                    and larg2 == rarg1
                                ):
                                    instructions.append(Instruction(Opcode.ADD))
                                    continue
                            case "-":
                                if (
                                    larg1 == rarg1
                                    and larg2 == rarg2
                                    or larg1 == rarg2
                                    and larg2 == rarg1
                                ):
                                    instructions.append(Instruction(Opcode.SUB))
                                    continue
                            case "+*":
                                if (
                                    larg1 == rarg1
                                    and larg2 == rarg2
                                    or larg1 == rarg2
                                    and larg2 == rarg1
                                ):
                                    instructions.append(Instruction(Opcode.MUL))
                                    continue
                            case "+/":
                                if larg1 == rarg1 and larg2 == rarg2:
                                    instructions.append(Instruction(Opcode.DIV))
                                    continue
                            case "&":
                                if (
                                    larg1 == rarg1
                                    and larg2 == rarg2
                                    or larg1 == rarg2
                                    and larg2 == rarg1
                                ):
                                    instructions.append(Instruction(Opcode.AND))
                                    continue
                            case "|":
                                if (
                                    larg1 == rarg1
                                    and larg2 == rarg2
                                    or larg1 == rarg2
                                    and larg2 == rarg1
                                ):
                                    instructions.append(Instruction(Opcode.OR))
                                    continue
                            case "^":
                                if (
                                    larg1 == rarg1
                                    and larg2 == rarg2
                                    or larg1 == rarg2
                                    and larg2 == rarg1
                                ):
                                    instructions.append(Instruction(Opcode.XOR))
                                    continue
                            case "==":
                                if (
                                    larg1 == rarg1
                                    and larg2 == rarg2
                                    or larg1 == rarg2
                                    and larg2 == rarg1
                                ):
                                    instructions.append(Instruction(Opcode.EQ))
                                    continue
                            case ">":
                                if (
                                    larg1 == rarg1
                                    and larg2 == rarg2
                                    or larg1 == rarg2
                                    and larg2 == rarg1
                                ):
                                    instructions.append(Instruction(Opcode.GT))
                                    continue
                            case "<":
                                if (
                                    larg1 == rarg1
                                    and larg2 == rarg2
                                    or larg1 == rarg2
                                    and larg2 == rarg1
                                ):
                                    instructions.append(Instruction(Opcode.LT))
                                    continue
                            case ">=":
                                if (
                                    larg1 == rarg1
                                    and larg2 == rarg2
                                    or larg1 == rarg2
                                    and larg2 == rarg1
                                ):
                                    instructions.append(Instruction(Opcode.GEQ))
                                    continue
                            case "<=":
                                if (
                                    larg1 == rarg1
                                    and larg2 == rarg2
                                    or larg1 == rarg2
                                    and larg2 == rarg1
                                ):
                                    instructions.append(Instruction(Opcode.LEQ))
                                    continue
                            case _:
                                raise Exception("Unexpected operator on the right")
                    elif no_r_args:
                        idx += self._calc_left_space(
                            line[idx:], len(no_r_args.group(0))
                        )
                        effect = self.effect.match(line, idx)
                        if not effect:
                            raise Exception("Unexpected operands sequence")
                        idx += self._calc_left_space(line[idx:], len(effect.group(0)))
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
                        idx += self._calc_left_space(
                            line[idx:], len(two_r_args.group(0))
                        )
                        rarg1, op, rarg2 = (
                            two_r_args.group(1),
                            two_r_args.group(2),
                            two_r_args.group(3),
                        )
                        match op:
                            case ",":
                                if larg == rarg1 and larg == rarg2:
                                    instructions.append(Instruction(Opcode.DUP))
                                    continue
                            case _:
                                raise Exception("Unexpected operator on the right")
                    elif one_r_arg:
                        idx += self._calc_left_space(
                            line[idx:], len(one_r_arg.group(0))
                        )
                        op, rarg = one_r_arg.group(1), one_r_arg.group(2)
                        if op:
                            if larg != rarg:
                                raise Exception("Argument mismatch")
                            match op:
                                case "~":
                                    instructions.append(Instruction(Opcode.INV))
                                    continue
                                case "-":
                                    instructions.append(Instruction(Opcode.NEG))
                                    continue
                                case "<<":
                                    instructions.append(Instruction(Opcode.SHLT))
                                    continue
                                case ">>":
                                    instructions.append(Instruction(Opcode.SHRT))
                                    continue
                                case _:
                                    raise Exception("Unknown unary operator")
                        if larg == rarg:
                            raise Exception("Argument duplication")
                        effect = self.effect.match(line, idx)
                        if not effect:
                            raise Exception("Unknown operands sequence")
                        idx += self._calc_left_space(line[idx:], len(effect.group(0)))
                        arrow, op = effect.group(1), effect.group(2)
                        if arrow != "<=":
                            raise Exception("Unexpected arrow direction")
                        match op:
                            case "MEM_DATA":
                                instructions.append(Instruction(Opcode.LOAD))
                                continue
                            case "IN":
                                instructions.append(Instruction(Opcode.IN))
                                continue
                            case _:
                                raise Exception("Unexpected effect on the right")
                    elif no_r_args:
                        idx += self._calc_left_space(
                            line[idx:], len(no_r_args.group(0))
                        )
                        effect = self.effect.match(line, idx)
                        if not effect:
                            instructions.append(Instruction(Opcode.POP))
                            continue
                        idx += self._calc_left_space(line[idx:], len(effect.group(0)))
                        arrow, op = effect.group(1), effect.group(2)
                        if arrow != "=>":
                            raise Exception("Unexpected arrow direction")
                        if op != "FLG":
                            raise Exception("Unexpected effect on the right")
                        instructions.append(Instruction(Opcode.SFLG))
                        continue
                    else:
                        raise Exception("Unsupported operands sequence")
                elif no_l_args:
                    idx += self._calc_left_space(line[idx:], len(no_l_args.group(0)))
                    one_r_arg = self.one_right_arg.match(line, idx)
                    no_r_args = self.no_right_args.match(line, idx)
                    if one_r_arg:
                        idx += self._calc_left_space(
                            line[idx:], len(one_r_arg.group(0))
                        )
                        op, rarg = one_r_arg.group(1), one_r_arg.group(2)
                        if op:
                            raise Exception("Unexpected unary operator")
                        effect = self.effect.match(line, idx)
                        if not effect:
                            instructions.append(Instruction(Opcode.PUSH, arg=rarg))
                            pc += 4
                            continue
                        idx += self._calc_left_space(line[idx:], len(effect.group(0)))
                        arrow, op = effect.group(1), effect.group(2)
                        if arrow != "<=":
                            raise Exception("Unexpected arrow direction")
                        if op != "FLG":
                            raise Exception("Unexpected effect on the right")
                        instructions.append(Instruction(Opcode.LFLG))
                        continue
                    elif no_r_args:
                        idx += self._calc_left_space(
                            line[idx:], len(no_r_args.group(0))
                        )
                        instructions.append(Instruction(Opcode.NOP))
                        continue
                    else:
                        raise Exception("Unsupported operands sequence")
                elif control_flow_match:
                    cf_content = control_flow_match.group(1).strip()
                    idx += self._calc_left_space(
                        line[idx:], offset=len(control_flow_match.group(0))
                    )
                    if cf_content == "...":
                        instructions.append(Instruction(Opcode.HLT))
                    elif cf_content == "RET":
                        instructions.append(Instruction(Opcode.RET))
                    elif cf_content.startswith("?"):
                        label = cf_content[1:].strip()
                        instructions.append(Instruction(Opcode.JMPIF, arg=label))
                        pc += 4
                    elif cf_content.startswith("!"):
                        label = cf_content[1:].strip()
                        instructions.append(Instruction(Opcode.CALL, arg=label))
                        pc += 4
                    else:
                        instructions.append(Instruction(Opcode.JMP, arg=cf_content))
                        pc += 4
                    continue
                else:
                    raise Exception(f"Unknown tokens found: {line[idx : idx + 16]}")

        return InstructionsSegment(address, instructions)

    def _find_next(self, code: str, start: int) -> int:
        d = Segment.data_regex.search(code, start)
        t = Segment.text_regex.search(code, start)
        matches = [m.start() for m in [d, t] if m]
        return min(matches) if matches else len(code)

    def _align_segments(
        self,
        segments: List[DataSegment | InstructionsSegment],
        labels: Dict[str, LabelDeclaration],
    ) -> Tuple[bytes, bytes]:
        if "_main" not in labels:
            raise Exception("Program has no entrypoint label '_main'!")

        data_pc: int = 0
        text_pc: int = 5
        for seg in segments:
            match seg:
                case DataSegment():
                    if seg.start is None:
                        seg.start = data_pc
                    if seg.start < data_pc:
                        raise Exception("Data segment overlap detected")
                    data_pc = seg.start + len(seg.data)
                case InstructionsSegment():
                    if seg.start is None:
                        seg.start = text_pc
                    if seg.start < text_pc:
                        raise Exception("Text segment overlap detected")
                    text_pc = seg.start + sum(
                        map(lambda x: 1 if x.arg is None else 5, seg.data)
                    )
                case _:
                    raise Exception("Unknown segment class")

        for name, label in labels.items():
            seg_start = segments[label.segment_idx].start
            if seg_start is None:
                raise Exception("Segment start is not resolved")
            labels[name].abs_addr = seg_start + label.offset

        data_dump: bytearray = bytearray(data_pc)
        text_dump: bytearray = bytearray(text_pc)

        if labels["_main"].abs_addr is None:
            raise Exception("Unresolved absolute address for entrypoint.")
        text_dump[0:5] = Opcode.JMP.value.to_bytes() + labels[
            "_main"
        ].abs_addr.to_bytes(4, byteorder="little")

        for seg in segments:
            if seg.start is None:
                raise Exception("Segment start is not resolved")
            match seg:
                case DataSegment():
                    data_dump[seg.start : seg.start + len(seg.data)] = seg.data
                case InstructionsSegment():
                    offset = seg.start
                    for instr in seg.data:
                        op_val = int(instr.opcode.value)
                        if instr.arg is None:
                            text_dump[offset : offset + 1] = op_val.to_bytes()
                            offset += 1
                            continue
                        arg_val: int = 0
                        match ArgType.get(instr.arg):
                            case ArgType.DEC:
                                arg_val = int(instr.arg)
                            case ArgType.HEX:
                                arg_val = int(instr.arg, 16)
                            case ArgType.LABEL:
                                if instr.arg not in labels:
                                    raise Exception(f"Undefined label: {instr.arg}")
                                label_addr = labels[instr.arg].abs_addr
                                if label_addr is None:
                                    raise Exception(
                                        f"Unresolved absolute address for label: {instr.arg}"
                                    )
                                arg_val = label_addr
                            case _:
                                raise Exception(
                                    f'Unknown argument "{instr.arg}" for instruction: {instr.opcode}'
                                )
                        text_dump[offset : offset + 5] = op_val.to_bytes(
                            1
                        ) + arg_val.to_bytes(4, byteorder="little")
                        offset += 5
                case _:
                    raise Exception("Unknown segment class")

        return bytes(data_dump), bytes(text_dump)

    def translate(self, code: str) -> Tuple[bytes, bytes]:
        idx = 0
        segments: List[DataSegment | InstructionsSegment] = list()
        labels: Dict[str, LabelDeclaration] = dict()
        while idx < len(code):
            d_match = Segment.data_regex.match(code, idx)
            i_match = Segment.text_regex.match(code, idx)
            if d_match:
                raw_addr = d_match.group(1)
                addr = self._parse_address(raw_addr)
                content_start = d_match.end()
                content_end = self._find_next(code, content_start)
                data_segment = self._translate_data(
                    len(segments), addr, code[content_start:content_end], labels
                )
                segments.append(data_segment)
                idx = content_end
            elif i_match:
                raw_addr = i_match.group(1)
                addr = self._parse_address(raw_addr)
                content_start = i_match.end()
                content_end = self._find_next(code, content_start)
                text_segment = self._translate_instructions(
                    len(segments), addr, code[content_start:content_end], labels
                )
                segments.append(text_segment)
                idx = content_end
            elif code[idx].isspace():
                idx += self._calc_left_space(code[idx:])
            else:
                raise Exception(
                    f"Unknown segment at index {idx}: {code[idx : idx + 15]!r}"
                )
        return self._align_segments(segments, labels)


def main(source: str, target: str) -> None:
    translator, preprocessor = Translator(), Preprocessor()

    with open(source, encoding="utf-8") as f:
        source = f.read()

    code = preprocessor.preprocess(source)
    bin_data, bin_code = translator.translate(code)

    os.makedirs(os.path.dirname(os.path.abspath(target)) or ".", exist_ok=True)
    with open(target + "_data.bin", "wb") as f:
        f.write(bin_data)
    with open(target + "_code.bin", "wb") as f:
        f.write(bin_code)
    with open(target + "_data.hex", "w") as f:
        f.write(Decoder.data_to_hex(bin_data))
    with open(target + "_code.hex", "w") as f:
        f.write(Decoder.code_to_hex(bin_code))


if __name__ == "__main__":
    assert len(sys.argv) == 3, (
        "Wrong arguments: translator.py <input_file> <target_prefix>"
    )
    _, source, target = sys.argv
    main(source, target)
