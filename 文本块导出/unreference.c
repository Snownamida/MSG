#pragma warning(disable:4996)
#include <stdlib.h>
#include<stdio.h>
#include "typeDef.h"


extern char* ROM_LOC;

struct string unreference_string_pointer(struct pointer_with_length string_ppu_pointer) {
	struct string string;
	FILE* ROM = fopen(ROM_LOC, "rb");
	if (!ROM) {
		printf("找不到ROM文件 请将ROM拖放至此程序的图标上");
		abort();
	}
	fseek(ROM, string_ppu_pointer.pointer, SEEK_SET);
	char Byte1 = getc(ROM);
	char Byte2 = getc(ROM);
	string.length = (Byte1) ? string_ppu_pointer.length : (Byte2 & 0b01111111) + 2;

	fseek(ROM, string_ppu_pointer.pointer, SEEK_SET);
	if (string.length > 32) {
#ifdef SHOW_block_to_string_unicode_DETAIL
		printf("字符串数居然超过了32, 字符串指针为%x的肯定有问题\n", string_pointer);
#endif // SHOW_block_to_string_unicode_DETAIL		
		string.length = 32;
	}
	for (int i = 0; i < string.length; i++) {
		string.string[i] = getc(ROM);
	}
	fclose(ROM);
	return string;
}

struct threeByte unreference_text_pointer(int text_pointer) {
	struct threeByte text;
	FILE* ROM = fopen(ROM_LOC, "rb");
	if (!ROM) {
		printf("找不到ROM文件 请将ROM拖放至此程序的图标上");
		abort();
	}
	fseek(ROM, text_pointer, SEEK_SET);
	text.byte1 = getc(ROM);
	text.byte2 = getc(ROM);
	text.byte3 = getc(ROM);
	fclose(ROM);
	return text;
}

struct string unreferernce_block_string_pointer(int block_string_pointer) {
	struct string block_string;
	FILE* ROM = fopen(ROM_LOC, "rb");
	if (!ROM) {
		printf("找不到ROM文件 请将ROM拖放至此程序的图标上");
		abort();
	}
	fseek(ROM, block_string_pointer, SEEK_SET);
	char block;

	for (int i = 0; ; i++) {
		if (i >= 512) {
			printf("文字块串居然超过了512字节\n");
			block_string.length = 512;
			break;
		}
		block_string.string[i] = getc(ROM);

		if (IS_DOUBLE_BYTE(block_string.string[i])) {
			i++;
			block_string.string[i] = getc(ROM);
			continue;
		}
		if (IS_TRIPLE_BYTE(block_string.string[i])) {
			i++;
			block_string.string[i] = getc(ROM);
			i++;
			block_string.string[i] = getc(ROM);
			continue;
		}

		if (block_string.string[i] == 0x00 || block_string.string[i] == 0x04 || block_string.string[i] == 0x06) {
			block_string.length = i + 1;
			break;
		}


	}
	fclose(ROM);
	return block_string;
}

struct threeByte unreference_sentance_pointer(int sentance_pointer) {
	struct threeByte sentance;
	FILE* ROM = fopen(ROM_LOC, "rb");
	if (!ROM) {
		printf("找不到ROM文件 请将ROM拖放至此程序的图标上");
		abort();
	}
	fseek(ROM, sentance_pointer, SEEK_SET);
	sentance.byte1 = getc(ROM);
	sentance.byte2 = getc(ROM);
	sentance.byte3 = getc(ROM);
	fclose(ROM);
	return sentance;
}