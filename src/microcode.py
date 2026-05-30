from typing import List, Dict, Tuple
from isa import Opcode
from controlunit import MicroInstruction, MuxPcSel, MuxMpcSel
from datapath import MuxTdSel, MuxSSel, MuxDataReadSel, MuxSrSel, AluOp

def generate_microprogram() -> Tuple[List[MicroInstruction], Dict[Tuple[Opcode, int], int]]:
  mprogram: List[MicroInstruction] = []
  state_decoder_map: Dict[Tuple[Opcode, int], int] = {}
  
  def add_instruction(inst: MicroInstruction) -> int:
    mprogram.append(inst)
    return len(mprogram) - 1

  fetch_idx = add_instruction(MicroInstruction(
    latch_ir_pipeline=True,
    latch_pc=True,
    select_pc=MuxPcSel.PC_PLUS_1,
    select_mpc=MuxMpcSel.STATE_DECODER,
    latch_mpc=True
  ))

  state_decoder_map[(Opcode.NOP, 0)] = add_instruction(MicroInstruction(
    select_mpc=MuxMpcSel.STATE_DECODER,
    latch_mpc=True,
    next_mpc_idx=fetch_idx
  ))

  state_decoder_map[(Opcode.HLT, 0)] = add_instruction(MicroInstruction(
    latch_mpc=False
  ))

  state_decoder_map[(Opcode.PUSH, 0)] = add_instruction(MicroInstruction(
    latch_td=True,
    select_td=MuxTdSel.NIR,
    latch_s=True,
    select_s=MuxSSel.TD_SHIFT,
    data_stack_push=True,
    latch_pc=True,
    select_pc=MuxPcSel.PC_PLUS_4,
    select_mpc=MuxMpcSel.STATE_DECODER,
    latch_mpc=True,
    next_mpc_idx=fetch_idx
  ))

  state_decoder_map[(Opcode.POP, 0)] = add_instruction(MicroInstruction(
    latch_s=True,
    select_s=MuxSSel.STACK_PREV,
    latch_td=True,
    select_td=MuxTdSel.S_SHIFT,
    select_mpc=MuxMpcSel.STATE_DECODER,
    latch_mpc=True,
    next_mpc_idx=fetch_idx
  ))

  state_decoder_map[(Opcode.ADD, 0)] = add_instruction(MicroInstruction(
    latch_td=True,
    select_td=MuxTdSel.ALU_RESULT,
    alu_op=AluOp.ADD,
    latch_s=True,
    select_s=MuxSSel.STACK_PREV,
    latch_sr=True,
    select_sr=MuxSrSel.ALU_FLAGS,
    select_mpc=MuxMpcSel.STATE_DECODER,
    latch_mpc=True,
    next_mpc_idx=fetch_idx
  ))

  state_decoder_map[(Opcode.SUB, 0)] = add_instruction(MicroInstruction(
    latch_td=True,
    select_td=MuxTdSel.ALU_RESULT,
    alu_op=AluOp.SUB,
    latch_s=True,
    select_s=MuxSSel.STACK_PREV,
    latch_sr=True,
    select_sr=MuxSrSel.ALU_FLAGS,
    select_mpc=MuxMpcSel.STATE_DECODER,
    latch_mpc=True,
    next_mpc_idx=fetch_idx
  ))

  state_decoder_map[(Opcode.JMP, 0)] = add_instruction(MicroInstruction(
    latch_pc=True,
    select_pc=MuxPcSel.I_PREFETCH,
    select_mpc=MuxMpcSel.STATE_DECODER,
    latch_mpc=True,
    next_mpc_idx=fetch_idx
  ))

  state_decoder_map[(Opcode.LOAD, 0)] = add_instruction(MicroInstruction(
    latch_td=True,
    select_td=MuxTdSel.DATA_READ,
    select_data_read=MuxDataReadSel.RAM,
    select_mpc=MuxMpcSel.STATE_DECODER,
    latch_mpc=True,
    next_mpc_idx=fetch_idx
  ))

  state_decoder_map[(Opcode.STORE, 0)] = add_instruction(MicroInstruction(
    write_memory=True,
    latch_s=True,
    select_s=MuxSSel.STACK_PREV,
    latch_td=True,
    select_td=MuxTdSel.S_SHIFT,
    select_mpc=MuxMpcSel.STATE_DECODER,
    latch_mpc=True,
    next_mpc_idx=fetch_idx
  ))

  state_decoder_map[(Opcode.IN, 0)] = add_instruction(MicroInstruction(
    latch_td=True,
    select_td=MuxTdSel.DATA_READ,
    select_data_read=MuxDataReadSel.IO,
    select_mpc=MuxMpcSel.STATE_DECODER,
    latch_mpc=True,
    next_mpc_idx=fetch_idx
  ))

  state_decoder_map[(Opcode.OUT, 0)] = add_instruction(MicroInstruction(
    write_io=True,
    latch_s=True,
    select_s=MuxSSel.STACK_PREV,
    latch_td=True,
    select_td=MuxTdSel.S_SHIFT,
    select_mpc=MuxMpcSel.STATE_DECODER,
    latch_mpc=True,
    next_mpc_idx=fetch_idx
  ))

  return mprogram, state_decoder_map