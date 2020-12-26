/*
        句子编号 -----sentance_number_to_sentance_pointer----> 句子指针 -----unreference_sentance_pointer---->         #指针（pointer）在这里指的就是ROM地址，
(sentance_number)                                                               (sentance_pointer)

    句子 -----sentance_to_block_string_pointer----> 文本块串指针 -----unreferernce_block_string_pointer---->                      #左表每新开一行都意味着进行了一层解引用（unreference），即去.nes文件里查找了相应的值
(sentance)                                             (block_string_pointer)

    文本块串 -----用for循环打散----> 文本块 -----block_to_text_pointer----> 文本指针  -----unreference_text_pointer---->
(block_string)                                 (block)                                              (text_pointer)

文本  -----text_to_string_pointer----> 字符串指针（包含一串有多少个） -----unreference_string_pointer---->
(text)                                           (string_ppu_pointer)


字符串(PPU编码) -----string_ppu_to_unicode----> 字符串(Unicode编码)
(string_ppu)                                                                (string_unicode)

句子编号: 从1到ADD的2781个句子

句子: 三个字节

文本块(block):  00~7F, 8080~8BFF中的一个值

文本(text): 三个字节
*/

#pragma warning(disable:4996)
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdbool.h>
#include "typeDef.h"
#include "unreference.h"
#include "value_calculate.h"
#include "expand_value_in_string.h"
//#define SHOW_block_to_string_unicode_DETAIL


char* ROM_LOC = "Metal Slader Glory (Japan).nes";


struct string block_show(int block) {


		int text_pointer = block_to_text_pointer(block);
		struct threeByte text = unreference_text_pointer(text_pointer);
		struct pointer_with_length string_ppu_pointer = text_to_string_pointer(text);
		struct string string_ppu = unreference_string_pointer(string_ppu_pointer);
		struct string string_unicode = string_ppu_to_unicode(string_ppu);

#ifdef SHOW_block_to_string_unicode_DETAIL
		printf("%02X\t%X\t%02X %02X %02X\t%X\t%d\t", block, text_pointer, text.byte1, text.byte2, text.byte3, string_ppu_pointer, string_ppu_length);
		for (int i = 0; i < string_ppu.length; i++) {
			unsigned char char_ppu = string_ppu.string[i];
			printf("%02X ", char_ppu);
			//			if (i && !string_ppu.string[i])printf("<-居然在字符串中间出现了00 ");
	}putchar('\t');
	printf("%s\n", string_unicode.string);
#endif // SHOW_block_to_string_unicode_DETAIL

	return string_unicode;
	


}
struct string sentance_show(struct string block_string) {
	struct string sentance_content = { .string = {0} };
		for (int block_count= 0; block_count < block_string.length; block_count++) {
			if (IS_TRIPLE_BYTE(block_string.string[block_count])) {
				char* code[16];
				int byte1 = block_string.string[block_count];
				int byte2 = block_string.string[++block_count];
				int byte3 = block_string.string[++block_count];
				snprintf(code, 16,"~%02X%02X%02X~", byte1, byte2, byte3);
				strcat_s(sentance_content.string, 2048, code);
				
				continue;
			}
			if (IS_DOUBLE_BYTE(block_string.string[block_count]) && block_string.string[block_count] < 0x80) {
				char* code[16];
				int byte1 = block_string.string[block_count];
				int byte2 = block_string.string[++block_count];
				snprintf(code,16, "~%02X%02X~", byte1, byte2);
				strcat_s(sentance_content.string, 2048, code);
				continue;
			}
			if (block_string.string[block_count] <0x80) {
				strcat_s(sentance_content.string, 2048, block_show(block_string.string[block_count]).string);
				continue;
			}
			if (block_string.string[block_count] >= 0x80) {
				int byte1 = block_string.string[block_count];
				int byte2 = block_string.string[++block_count];
				strcat_s(sentance_content.string, 2048, block_show((byte1 <<8)+ byte2).string);
				continue;
				
			}

			
		}

		return sentance_content;
}

void print_all_blocks(void) {
	printf("字符块\t文本指针\t文本\t字符串指针\t字符串长度\t字符串\n");
	for (int block_generator = block_start; block_generator <= block_end; block_generator++) {
		int block = (block_generator > 0x807F) ? block_generator : block_generator - 0x8000;
		struct string string_unicode = block_show(block);
		printf("%s\n", string_unicode.string);
	}

}
void print_all_sentance(void) {
	for (unsigned int sentance_number = 1; sentance_number <= sentance_total; sentance_number++) {
		struct string block_string = sentance_number_to_block_string(sentance_number);
		struct string string_ppu = block_string_to_string_ppu(block_string);
		struct string string_unicode = string_ppu_to_unicode(string_ppu);
		printf("%d\t%s\n", sentance_number, string_unicode.string);
	}
}

int main(int argc, char* argv[]) { 
	if (argc == 2)ROM_LOC = argv[1];
	print_all_blocks();
	print_all_sentance();
	return 2333;
}