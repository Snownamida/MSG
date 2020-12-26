//**************************************数值计算、转换**************************************
#pragma warning(disable:4996)
#include <stdlib.h>
#include<stdio.h>
#include "typeDef.h"



struct pointer_with_length text_to_string_pointer(struct threeByte text) {
	struct pointer_with_length string_pointer;
	string_pointer.pointer = (((text.byte1 & 0b00111111) - 0x2A) << 13) + ((text.byte3 & 0b00011111 ^ 0b10100000) << 8) + text.byte2 + 0x4A010;
	string_pointer.length = (text.byte1 >> 6 << 3) + (text.byte3 >> 5);
	return string_pointer;
}

int block_to_text_pointer(int block) {
	block = (block > 0x7F) ? block : block + 0x8000;
	return 3 * (block - 0x8000) + 0x3D5C;
}

int  sentance_to_block_string_pointer(struct threeByte sentance) {
	return 0x56010 + (((sentance.byte1 & 0b01111111) - 0x30) * 0x2000) + ((sentance.byte3 + 0xA0) << 8) + sentance.byte2;
}

int sentance_number_to_sentance_pointer(int sentance_number) {
	return 3 * (sentance_number - 1) + sentance_pointer_start;
}