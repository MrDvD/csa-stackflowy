from typing import Any, List
import contextlib
import io
import logging
import os
import tempfile
import machine
import pytest
import translator


MAX_LOG = 4000


@pytest.mark.golden_test("golden/*.yml")
def test_translator_and_machine(golden: Any, caplog: pytest.LogCaptureFixture) -> None:
    logging.setLoggerClass(machine.SlicingLogger)

    with tempfile.TemporaryDirectory() as tmpdirname:
        source: str = os.path.join(tmpdirname, "source.bf")

        port_streams = {
            0: os.path.join(tmpdirname, "port0.txt"),
            1: os.path.join(tmpdirname, "port1.txt"),
            2: os.path.join(tmpdirname, "port2.txt"),
            3: os.path.join(tmpdirname, "port3.txt"),
        }

        target_prefix: str = os.path.join(tmpdirname, "target")

        with open(source, "w", encoding="utf-8") as file:
            file.write(golden["in_source"])
        for port_id, file_path in port_streams.items():
            with open(file_path, "w", encoding="utf-8") as f:
                port_input: List[Any] | str = golden.get("port_mapped_io", {}).get(
                    port_id, ""
                )
                if isinstance(port_input, list):
                    f.write("".join(map(chr, port_input)))
                else:
                    f.write(port_input)

        with contextlib.redirect_stdout(io.StringIO()) as stdout:
            translator.main(source, target_prefix)
            machine.main(
                target_prefix,
                port_streams[0],
                port_streams[1],
                port_streams[2],
                port_streams[3],
                golden["data_memory_size"],
                golden["text_memory_size"],
                golden["limit"],
                golden["view"],
                golden.get("slice", "all"),
            )

        with open(target_prefix + "_data_final.bin", "rb") as file:
            data: bytes = file.read()
        with open(target_prefix + "_data_final.hex", encoding="utf-8") as file:
            data_hex: str = file.read()
        with open(target_prefix + "_code.bin", "rb") as file:
            text: bytes = file.read()
        with open(target_prefix + "_code.hex", encoding="utf-8") as file:
            text_hex: str = file.read()

        stdout_captured = stdout.getvalue()
        print(stdout_captured)

        assert data == golden.out["out_data"]
        assert data_hex == golden.out["out_data_hex"]
        assert text == golden.out["out_text"]
        assert text_hex == golden.out["out_text_hex"]
        assert stdout_captured == golden.out["out_stdout"]
        assert caplog.text[:MAX_LOG] == golden.out["out_log"][:MAX_LOG]
