from datapath import DataPath
from controlunit import ControlUnit
from isa import Decoder
from microcode import generate_microprogram
from typing import List
import logging
import sys


class Processor:
    def __init__(
        self,
        data_memory_size: int,
        text_memory_size: int,
        input_data: List[List[int]],
        view_template: str,
    ):
        self.data_path: DataPath = DataPath(data_memory_size, input_data)
        mprogram, state_decoder_map = generate_microprogram()
        self.control_unit: ControlUnit = ControlUnit(
            text_memory_size, mprogram, state_decoder_map, self.data_path, view_template
        )

    def load_text(self, text_code: bytes) -> None:
        for idx, byte in enumerate(text_code):
            if idx < len(self.control_unit.rom_instructions):
                self.control_unit.rom_instructions[idx] = byte

    def load_data(self, data_code: bytes) -> None:
        for idx in range(0, len(data_code), 4):
            chunk = data_code[idx : idx + 4]
            if len(chunk) < 4:
                chunk = chunk.ljust(4, b"\x00")

            data_in = int.from_bytes(chunk, byteorder="big")
            self.data_path.data_memory.write(idx, data_in)

    def run(self, limit: int) -> tuple[str, int]:
        model_tick: int = 0
        try:
            while model_tick < limit and self.control_unit.mr.micromem_output:
                stalled = self.control_unit.tick()
                logging.debug(
                    f"{model_tick} [{'S' if stalled else ' '}] | {self.control_unit}"
                )
                model_tick += 1
                if model_tick == 726:
                    continue
        except Exception as e:
            raise e

        if model_tick >= limit:
            logging.warning("Limit exceeded!")

        output: str = ""
        for port in range(4):
            io_device = self.data_path.io_devices[port]
            output += f"outputbuffer[{port}]: {repr(io_device.output_buffer)}\n"
        return output, model_tick


class SlicingLogger(logging.Logger):
    slice_cfg: List[str] | str = "all"
    buffer: List[logging.LogRecord] = list()
    original_handle = logging.root.handle

    @classmethod
    def flush_sliced(cls):
        sliced = cls.buffer
        if cls.slice_cfg == "last":
            sliced = cls.buffer[-1:] if cls.buffer else []
        elif isinstance(cls.slice_cfg, list) and len(cls.slice_cfg) == 2:
            mode, n = cls.slice_cfg
            try:
                n = int(n)
                if mode == "head":
                    sliced = cls.buffer[:n]
                elif mode == "tail":
                    sliced = cls.buffer[-n:]
                else:
                    pass
            except (ValueError, TypeError):
                pass

        for record in sliced:
            cls.original_handle(record)
        cls.buffer.clear()


def _custom_handle(record: logging.LogRecord) -> None:
    if record.levelno == logging.DEBUG:
        SlicingLogger.buffer.append(record)
    else:
        SlicingLogger.original_handle(record)


logging.root.handle = _custom_handle


def main(
    target_prefix: str,
    input_file_1: str,
    input_file_2: str,
    input_file_3: str,
    input_file_4: str,
    data_mem_size: int,
    limit: int,
    view_template: str,
) -> None:
    with open(target_prefix + "_code.bin", "rb") as file:
        text_code: bytes = file.read()

    with open(target_prefix + "_data.bin", "rb") as file:
        data_code: bytes = file.read()

    input_data: List[List[int]] = list()
    for file in [input_file_1, input_file_2, input_file_3, input_file_4]:
        with open(file, encoding="ascii") as file:
            text: str = file.read()
            data: list[int] = [ord(char) for char in text]
            input_data.append(data)

    processor: Processor = Processor(
        data_memory_size=int(data_mem_size),
        text_memory_size=len(text_code),
        input_data=input_data,
        view_template=view_template,
    )
    processor.load_text(text_code)
    processor.load_data(data_code)

    try:
        output, ticks = processor.run(limit)
    finally:
        SlicingLogger.flush_sliced()

    final_mem_bytes = bytes(processor.data_path.data_memory.memory)
    with open(target_prefix + "_data_final.bin", "wb") as f:
        f.write(final_mem_bytes)
    with open(target_prefix + "_data_final.hex", "w", encoding="utf-8") as f:
        f.write(Decoder.data_to_hex(final_mem_bytes))

    print("".join(output))
    print("ticks:", ticks)


if __name__ == "__main__":
    logging.getLogger().setLevel(logging.DEBUG)
    if len(sys.argv) != 9:
        print(
            "Wrong arguments: machine.py <target_prefix> <input_file_1> ... <input_file_4> <data_mem_size> <limit> <view_template>"
        )
        sys.exit(1)
    (
        _,
        target_prefix,
        input_file_1,
        input_file_2,
        input_file_3,
        input_file_4,
        data_mem_size,
        limit,
        view_template,
    ) = sys.argv
    if not data_mem_size.isdecimal():
        print("Wrong arguments: <data_mem_size> is not a decimal number")
        sys.exit(1)
    if not limit.isdecimal():
        print("Wrong arguments: <limit> is not a decimal number")
        sys.exit(1)
    main(
        target_prefix,
        input_file_1,
        input_file_2,
        input_file_3,
        input_file_4,
        int(data_mem_size),
        int(limit),
        view_template,
    )
