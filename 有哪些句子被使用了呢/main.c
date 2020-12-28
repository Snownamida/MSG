#pragma warning(disable:4996)
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdbool.h>

char* CDL_LOC = "Metal Slader Glory (Japan).cdl";

int main(int argc, char* argv[]) {

	struct Bytes
	{
		unsigned char byte;
		bool beenRead;
	};

	struct Bytes* cdl = malloc(sizeof(struct Bytes)*0x80010);
	memset(cdl, 0, sizeof(struct Bytes) * 0x80010);
	FILE* CDL = fopen(CDL_LOC, "rb");
	if (!CDL) {
		printf("找不到CDL文件 请将CDL拖放至此程序的图标上");
		exit(9);
	}
	for (unsigned int i = 0; i < 0x80010; i++) {
		cdl[i].byte = getc(CDL);
	}
	fclose(CDL);

	int sentances = 0;
	printf("有以下句子被使用过了\n句子编号\t句子指针\t被使用时位于bank\n");
	for (unsigned int i = 0x1CB5; i < 0x3D4B; i += 3) {

		if (cdl[i].byte & 0b00000010) {
		printf("%d\t",(i-0x1CB5)/3+1);
		printf("%x\t",i+0x10);
		printf("%d\n",(cdl[i].byte&0b00001100)>>2);
		sentances++;
		}
		
	}

	printf("一共使用了%d个句子", sentances);
	return 2333;
}


/*
CDL files are just a mask of the ROM; that is, they are of the same size as the ROM, and each byte represents the corresponding byte of the ROM. The format of each byte is like so (in binary):




For PRG ROM:

x P d c A A D C

	   C = Whether it was accessed as code.

	   D = Whether it was accessed as data.

	   AA = Into which ROM bank it was mapped when last accessed:

			   00 = $8000-$9FFF        01 = $A000-$BFFF

			   10 = $C000-$DFFF        11 = $E000-$FFFF

	   c = Whether indirectly accessed as code.

			   (e.g. as the destination of a JMP ($nnnn) instruction)

	   d = Whether indirectly accessed as data.

			   (e.g. as the destination of an LDA ($nn),Y instruction)

	   P = If logged as PCM audio data.

	   x = unused.




For CHR ROM:

x x x x x x R D

	   D = Whether it was drawn on screen (rendered by PPU at runtime)

	   R = Whether it was read programmatically using port $2007

			   (e.g. Argus_(J).nes checks if the bankswitching works by reading the same byte of CHR data before and after switching)

	   x = unused.


*/