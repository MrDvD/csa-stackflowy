from typing import List, Dict, Tuple
from isa import Opcode
from dataclasses import dataclass, fields
from mux import (
    MuxPcSel,
    MuxTrSel,
    MuxMpcSel,
    MuxIPrefetch,
    MuxRStack,
    MuxTdSel,
    MuxSSel,
    MuxAluLeftSel,
    MuxAluRightSel,
    MuxDataReadSel,
    MuxSrSel,
    AluOp,
)


@dataclass(frozen=True)
class MicroInstruction:
    alu_op: AluOp = AluOp.ADD
    alu_l_sel: MuxAluLeftSel = MuxAluLeftSel.S
    alu_r_sel: MuxAluRightSel = MuxAluRightSel.TD
    latch_d_stack: bool = False
    latch_s: bool = False
    latch_td: bool = False
    select_s: MuxSSel = MuxSSel.NEXT
    select_td: MuxTdSel = MuxTdSel.ALU_RESULT
    latch_r_stack: bool = False
    latch_tr: bool = False
    select_r_stack: MuxRStack = MuxRStack.PREV
    select_tr: MuxTrSel = MuxTrSel.PC
    latch_pc: bool = False
    select_pc: MuxPcSel = MuxPcSel.PC_PLUS_1
    latch_sr: bool = False
    select_sr: MuxSrSel = MuxSrSel.ALU_RESULT
    memory_d_output: bool = False
    memory_i_output: bool = False
    memory_d_write: bool = False
    cache_i_write: bool = False
    io_output: bool = False
    io_write: bool = False
    select_data_read: MuxDataReadSel = MuxDataReadSel.MEM_DATA
    latch_ir: bool = False
    latch_i_prefetch: bool = False
    select_i_prefetch: MuxIPrefetch = MuxIPrefetch.PREV
    latch_mpc: bool = True
    latch_mr: bool = True
    micromem_output: bool = True
    select_mpc: MuxMpcSel = MuxMpcSel.STATE_DECODER

    def _get_str(self) -> str:
        active_signals: List[str] = list()

        for field in fields(self):
            current_value = getattr(self, field.name)
            default_value = field.default

            if current_value != default_value:
                if isinstance(current_value, bool):
                    if current_value:
                        active_signals.append(f"{field.name.upper()}")
                    else:
                        active_signals.append(f"NOT_{field.name.upper()}")
                else:
                    val_str = (
                        current_value.name
                        if hasattr(current_value, "name")
                        else str(current_value)
                    )
                    active_signals.append(f"{field.name.upper()}: {val_str}")

        if not active_signals:
            return "[DEFAULT]"

        return f"[ {' | '.join(active_signals)} ]"

    def __str__(self) -> str:
        return self._get_str()

    def __repr__(self) -> str:
        return self._get_str()


@dataclass(frozen=True)
class State:
    instruction: Opcode
    td_zero_bit: bool


def generate_microprogram() -> Tuple[List[MicroInstruction], Dict[State, int]]:
    mprogram: List[MicroInstruction] = list()
    state_decoder_map: Dict[State, int] = dict()

    def add_instruction(inst: MicroInstruction) -> int:
        mprogram.append(inst)
        return len(mprogram) - 1

    def reg_state(opcode: Opcode, start_idx: int, td: bool | None = None) -> None:
        if td is None:
            state_decoder_map[State(instruction=opcode, td_zero_bit=True)] = start_idx
            state_decoder_map[State(instruction=opcode, td_zero_bit=False)] = start_idx
            return
        state_decoder_map[State(instruction=opcode, td_zero_bit=td)] = start_idx

    fetch_argument = MicroInstruction(
        select_i_prefetch=MuxIPrefetch.CACHE_ARG,
        latch_i_prefetch=True,
        select_mpc=MuxMpcSel.MPC_PLUS_1,
    )

    # start of the mprogram
    add_instruction(
        MicroInstruction(  # fill i_prefetch if needed
            select_i_prefetch=MuxIPrefetch.CACHE,
            latch_i_prefetch=True,
            select_mpc=MuxMpcSel.MPC_PLUS_1,
        )
    )
    add_instruction(
        MicroInstruction(  # fetch instruction
            latch_pc=True,
            latch_ir=True,
            latch_i_prefetch=True,
            select_mpc=MuxMpcSel.MPC_PLUS_1,
        )
    )
    add_instruction(MicroInstruction())  # decode address of next instruction

    ### NOP
    idx = add_instruction(
        MicroInstruction(
            select_mpc=MuxMpcSel.START,
        )
    )
    reg_state(Opcode.NOP, idx)

    ### HALT
    idx = add_instruction(
        MicroInstruction(
            micromem_output=False,
        )
    )
    reg_state(Opcode.HLT, idx)

    ### JUMP
    idx = add_instruction(fetch_argument)
    add_instruction(
        MicroInstruction(
            latch_pc=True,
            select_pc=MuxPcSel.I_PREFETCH,
            select_mpc=MuxMpcSel.START,
        )
    )
    reg_state(Opcode.JMP, idx)

    ### JUMPIF
    success_idx = add_instruction(fetch_argument)
    add_instruction(
        MicroInstruction(
            latch_td=True,
            latch_s=True,
            select_td=MuxTdSel.S,
            select_s=MuxSSel.PREV,
            latch_d_stack=True,
            latch_pc=True,
            select_pc=MuxPcSel.I_PREFETCH,
            select_mpc=MuxMpcSel.START,
        )
    )
    failure_idx = add_instruction(fetch_argument)
    add_instruction(
        MicroInstruction(
            latch_td=True,
            latch_s=True,
            select_td=MuxTdSel.S,
            select_s=MuxSSel.PREV,
            latch_d_stack=True,
            latch_pc=True,
            select_pc=MuxPcSel.PC_PLUS_4,
            select_mpc=MuxMpcSel.START,
        )
    )
    reg_state(Opcode.JMPIF, success_idx, td=True)
    reg_state(Opcode.JMPIF, failure_idx, td=False)

    ### PUSH
    idx = add_instruction(fetch_argument)
    add_instruction(
        MicroInstruction(
            latch_td=True,
            select_td=MuxTdSel.I_PREFETCH,
            latch_s=True,
            latch_d_stack=True,
            latch_pc=True,
            select_pc=MuxPcSel.PC_PLUS_4,
            select_mpc=MuxMpcSel.START,
        )
    )
    reg_state(Opcode.PUSH, idx)

    ### DUP
    idx = add_instruction(
        MicroInstruction(
            latch_s=True,
            latch_d_stack=True,
            select_mpc=MuxMpcSel.START,
        )
    )
    reg_state(Opcode.DUP, idx)

    ### POP
    idx = add_instruction(
        MicroInstruction(
            latch_td=True,
            select_td=MuxTdSel.S,
            latch_s=True,
            select_s=MuxSSel.PREV,
            latch_d_stack=True,
            select_mpc=MuxMpcSel.START,
        )
    )
    reg_state(Opcode.POP, idx)

    ### BINARY ALU OPERATIONS
    def add_binary_op(opcode: Opcode, alu: AluOp) -> None:
        idx = add_instruction(
            MicroInstruction(
                latch_td=True,
                latch_s=True,
                latch_d_stack=True,
                select_s=MuxSSel.PREV,
                alu_op=alu,
                select_td=MuxTdSel.ALU_RESULT,
                select_mpc=MuxMpcSel.START,
            )
        )
        reg_state(opcode, idx)

    add_binary_op(Opcode.ADD, AluOp.ADD)
    add_binary_op(Opcode.SUB, AluOp.SUB)
    add_binary_op(Opcode.MUL, AluOp.MUL)
    add_binary_op(Opcode.DIV, AluOp.DIV)
    add_binary_op(Opcode.AND, AluOp.AND)
    add_binary_op(Opcode.OR, AluOp.OR)
    add_binary_op(Opcode.XOR, AluOp.XOR)
    add_binary_op(Opcode.SHLT, AluOp.SHLT)
    add_binary_op(Opcode.SHRT, AluOp.SHRT)
    add_binary_op(Opcode.INV, AluOp.NOT)
    add_binary_op(Opcode.NEG, AluOp.NEG)
    add_binary_op(Opcode.EQ, AluOp.EQ)
    add_binary_op(Opcode.GT, AluOp.GT)
    add_binary_op(Opcode.LT, AluOp.LT)
    add_binary_op(Opcode.GEQ, AluOp.GEQ)
    add_binary_op(Opcode.LEQ, AluOp.LEQ)

    ### SWAP
    idx = add_instruction(
        MicroInstruction(
            latch_td=True,
            latch_s=True,
            select_td=MuxTdSel.S,
            select_s=MuxSSel.NEXT,
            select_mpc=MuxMpcSel.START,
        )
    )
    reg_state(Opcode.SWAP, idx)

    ### LOAD
    idx = add_instruction(
        MicroInstruction(
            memory_d_output=True,
            latch_td=True,
            select_td=MuxTdSel.DATA_READ,
            select_mpc=MuxMpcSel.START,
        )
    )
    reg_state(Opcode.LOAD, idx)

    ### OUT
    idx = add_instruction(
        MicroInstruction(
            io_write=True,
            latch_td=True,
            select_td=MuxTdSel.DATA_STACK,
            select_s=MuxSSel.PREV_TWO,
            latch_d_stack=True,
            latch_s=True,
            select_mpc=MuxMpcSel.START,
        )
    )
    reg_state(Opcode.OUT, idx)

    return mprogram, state_decoder_map
