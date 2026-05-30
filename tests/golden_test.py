from typing import Any
import contextlib
import io
import logging
import os
import tempfile
import machine
import pytest
import translator

MAX_LOG: int = 4000


@pytest.mark.golden_test("golden/*.yml")
def test_translator_and_machine(golden: Any, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)

    with tempfile.TemporaryDirectory() as tmpdirname:
        source: str = os.path.join(tmpdirname, "source.bf")
        input_stream: str = os.path.join(tmpdirname, "input.txt")
        target_prefix: str = os.path.join(tmpdirname, "target")
        target_data: str = target_prefix + "_data.bin"
        target_data_hex: str = target_prefix + "_data.hex"
        target_code: str = target_prefix + "_code.bin"
        target_code_hex: str = target_prefix + "_code.hex"

        with open(source, "w", encoding="utf-8") as file:
            file.write(golden["in_source"])
        with open(input_stream, "w", encoding="utf-8") as file:
            file.write(golden["in_stdin"])

        with contextlib.redirect_stdout(io.StringIO()) as stdout:
            translator.main(source, target_prefix)
            print("============================================================")
            machine.main(
                target_data,
                target_code,
                input_stream,
                golden["data_memory_size"],
                golden["limit"],
            )

        with open(target_data, "rb") as file:
            data_code: bytes = file.read()
        with open(target_data_hex, encoding="utf-8") as file:
            data_code_hex: str = file.read()
        with open(target_code, "rb") as file:
            text_code: bytes = file.read()
        with open(target_code_hex, encoding="utf-8") as file:
            text_code_hex: str = file.read()

        assert data_code == golden.out["out_data"]
        assert data_code_hex == golden.out["out_data_hex"]
        assert text_code == golden.out["out_text"]
        assert text_code_hex == golden.out["out_text_hex"]
        assert stdout.getvalue() == golden.out["out_stdout"]
        assert caplog.text[0:MAX_LOG] + "EOF" == golden.out["out_log"]
