.set noreorder
.set noat
.text
    .space 8
n_value:
    .word 10

# Transparent wrapper: saves ALL GPRs (except zero,k0,k1,gp,sp) + HI/LO, runs the
# N-1 extra picks, restores everything, reloads $a0 (the stolen lw), resumes vanilla.
loop_entry:
    addiu $sp, $sp, -0x90
    sw    $at, 0x10($sp)
    sw    $v0, 0x14($sp)
    sw    $v1, 0x18($sp)
    sw    $a0, 0x1c($sp)
    sw    $a1, 0x20($sp)
    sw    $a2, 0x24($sp)
    sw    $a3, 0x28($sp)
    sw    $t0, 0x2c($sp)
    sw    $t1, 0x30($sp)
    sw    $t2, 0x34($sp)
    sw    $t3, 0x38($sp)
    sw    $t4, 0x3c($sp)
    sw    $t5, 0x40($sp)
    sw    $t6, 0x44($sp)
    sw    $t7, 0x48($sp)
    sw    $s0, 0x4c($sp)
    sw    $s1, 0x50($sp)
    sw    $s2, 0x54($sp)
    sw    $s3, 0x58($sp)
    sw    $s4, 0x5c($sp)
    sw    $s5, 0x60($sp)
    sw    $s6, 0x64($sp)
    sw    $s7, 0x68($sp)
    sw    $t8, 0x6c($sp)
    sw    $t9, 0x70($sp)
    sw    $fp, 0x74($sp)
    sw    $ra, 0x78($sp)
    mfhi  $t0
    mflo  $t1
    sw    $t0, 0x7c($sp)
    sw    $t1, 0x80($sp)
    lui   $t1, 0x801d
    ori   $t1, $t1, 0xb038
    lbu   $t1, 0($t1)
    nop
    addiu $s2, $t1, -1
    blez  $s2, done
    nop
    lw    $t2, 0x2e0($gp)
    nop
    lbu   $t3, 0x38($t2)
    lbu   $t4, 0x39($t2)
    sltiu $t5, $t3, 3
    beqz  $t5, else_branch
    nop
    addiu $s1, $zero, 1
    b     after_category
    nop
else_branch:
    sltu  $t4, $zero, $t4
    sll   $s1, $t4, 1
after_category:
loop_top:
    jal   0x8008e590
    nop
    andi  $a1, $v0, 0x7ff
    move  $a0, $s1
    jal   0x80021810
    nop
    addiu $t6, $v0, -1            # v8: valid pick is 1..722 (0 and >722 are skipped)
    sltiu $t6, $t6, 722
    beqz  $t6, next_iter          # invalid: do NOT grant (GrantCard(0) corrupts deck[39])
    nop
    move  $a0, $v0
    jal   0x80021894
    nop
next_iter:
    addiu $s2, $s2, -1
    bgtz  $s2, loop_top
    nop
done:
    lw    $t0, 0x7c($sp)
    lw    $t1, 0x80($sp)
    mthi  $t0
    mtlo  $t1
    lw    $at, 0x10($sp)
    lw    $v0, 0x14($sp)
    lw    $v1, 0x18($sp)
    lw    $a1, 0x20($sp)
    lw    $a2, 0x24($sp)
    lw    $a3, 0x28($sp)
    lw    $t0, 0x2c($sp)
    lw    $t1, 0x30($sp)
    lw    $t2, 0x34($sp)
    lw    $t3, 0x38($sp)
    lw    $t4, 0x3c($sp)
    lw    $t5, 0x40($sp)
    lw    $t6, 0x44($sp)
    lw    $t7, 0x48($sp)
    lw    $s0, 0x4c($sp)
    lw    $s1, 0x50($sp)
    lw    $s2, 0x54($sp)
    lw    $s3, 0x58($sp)
    lw    $s4, 0x5c($sp)
    lw    $s5, 0x60($sp)
    lw    $s6, 0x64($sp)
    lw    $s7, 0x68($sp)
    lw    $t8, 0x6c($sp)
    lw    $t9, 0x70($sp)
    lw    $fp, 0x74($sp)
    lw    $ra, 0x78($sp)
    lw    $a0, 0x2e0($gp)
    addiu $sp, $sp, 0x90
    j     0x80021c70
    nop
