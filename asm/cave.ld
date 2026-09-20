SECTIONS { . = 0x801db030; .text : { *(.text) } /DISCARD/ : { *(.MIPS.abiflags) *(.reginfo) *(.gnu.attributes) *(.pdr) *(.mdebug*) } }
