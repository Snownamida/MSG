path="C:/Users/snownamida/Desktop/FC/metal slader glory/MSG SVN/4_debug_script/" --请替换成自己的路径
-------------------------通用函数-------------------
function table.unique(t)
    local check = {}
    local n = {}
    local idx = 1
    for k, v in pairs(t) do
        if not check[v] then
             n[idx] = v
             idx = idx + 1
            check[v] = true
        end
    end
    return n
end

function string.unique(t)
	local check = {}
	local n = ""
	for i=1,string.len(t) do
		local chara=string.sub(t, i ,i)
		if not check[chara] then
			n=n..string.sub(t, i ,i)
			check[chara] = true
		end
	end
	return n
end
----------------------------------------------------------
function show_translate(sentence_number)
	tranFile=io.open(path.."translate_for_lua.txt", "r") 
	io.input(tranFile)
	for i=1,sentence_number do
		io.read()

	end
	sentence=string.format(io.read())
	io.close(tranFile)
	return sentence
end

function print_background_bank()

	if (memory.readbyte(0x0450) ~= background_bank) 
	then	
		background_bank=memory.readbyte(0x0450)
		emu.print(string.format("-----当前背景bank: %02X-----",background_bank))	
	end
end

function print_sentence_number()
	if(sentence_for_back==nil)then
		sentence_for_back={}
	end
	
	if (memory.readword(0x87)>=0xA000 and memory.readword(0x87)<0xBD4B and memory.readbyte(0xA000)==rom.readbyte(0x2010)  ) then
		sentence_number = (memory.readword(0x87)-0xA000)/3 +281
		emu.print(   string.format(   "使用了句子:%d ",sentence_number ) ,show_translate(sentence_number)  )	
		if(sentence_for_back[background_bank]==nil)then
			sentence_for_back[background_bank]={}
		end
		table.insert(sentence_for_back[background_bank],sentence_number )
		show_translate(sentence_number )
	end

	--因为只有PRG ROM 00是以0x00开头的, 所以可以作为它的标志. 而只有PRG ROM 01是0x36开头的, 但这个可能会在汉化过程中被换掉
	if (memory.readword(0x87)>=0xBCB5 and memory.readword(0x87)<0xBFFF and memory.readbyte(0xA000)==rom.readbyte(0x10)  ) then
		sentence_number =(memory.readword(0x87)-0xBCB5)/3 
		emu.print(   string.format(   "使用了句子:%d ",sentence_number ) ,show_translate(sentence_number)  )	
		if(sentence_for_back[background_bank]==nil)then
			sentence_for_back[background_bank]={}
		end
		table.insert(sentence_for_back[background_bank],sentence_number )
		show_translate(sentence_number)
	end


end

function show_sentence_for_back()
	if(sentence_for_back)then
		for b,s in pairs(sentence_for_back)do
			s=table.unique(s)
			table.sort(s)
			emu.print("背景",string.format("%X",b),"使用了句子",table.concat(s," "))
			used_chara=""
			for no,sentence_number in pairs(s) do
				used_chara=used_chara..show_translate(sentence_number)
				--used_chara=string.unique(used_chara)
			end
			emu.print(used_chara)
		end
	else
		emu.print("没有检测到任何句子")
	end
	
end

function press(botton)
	joypad.set(1,{[botton]=true})
	emu.frameadvance()
	joypad.set(1,{[botton]=false})
end

function wrong_input_for_VMH()
	while (memory.readbyte(0x15)~=0xFF) do
		emu.frameadvance()	--等待可以输入代码

	end
	press("up")
	emu.frameadvance()
	emu.frameadvance()
	press("right")
	emu.frameadvance()
	emu.frameadvance()
	press("up")
	emu.frameadvance()
	emu.frameadvance()
	press("right")
	emu.frameadvance()
	emu.frameadvance()
	press("up")
	emu.frameadvance()
	emu.frameadvance()
	press("A")

end

function wrong_input_for_MH()
	while (memory.readbyte(0x15)~=0xFF) do
		emu.frameadvance()	--等待可以输入代码

	end
	press("up")
	emu.frameadvance()
	emu.frameadvance()
	press("right")
	emu.frameadvance()
	emu.frameadvance()
	press("up")
	emu.frameadvance()
	emu.frameadvance()
	press("A")

end

--如果等到了,返回true;如果timer转了一个轮回都没等到,返回false
function wait_for_option_ready(exit_if_cant_wait)
	local wait_for=0x10
	timer=memory.readbyte(0x9D)
	while (memory.readbyte(0x17)~=wait_for) do
		emu.frameadvance()
		if(memory.readbyte(0x9D)==timer-1 and exit_if_cant_wait)then
			return false
		end
	end
	return true
end

function press_for_option(botton,times)
	for i=1,times do
		wait_for_option_ready()
		press(botton)
	end

end

function next_para(times)
	if(type(times)=="number")then
		for i=1,times do
			while(memory.readbyte(0x0200)~=0xF0) do
				emu.frameadvance()
			end
		press("A")
		end
	end

	if(type(times)=="string")then
		while(wait_for_option_ready(true)==false)do

			while(memory.readbyte(0x0200)~=0xF0) do
				emu.frameadvance()
			end
		press("A")
		end
	end

	
end

function option_view(option_number,repeat_times,dont_reset_position)
	for repeat_time=1,repeat_times do
		i=1
		while(option_number[i]) do
			wait_for_option_ready()
			while(memory.readbyte(0x2C)~=option_number[i]-1) do
				press_for_option("down",1)
				wait_for_option_ready()
			end
			press_for_option("A",1)
			i=i+1
		end
		i=i-1
		next_para("to_next_option")
	
		
		if (not dont_reset_position) then
			while(option_number[i]) do
				wait_for_option_ready()
				while(memory.readbyte(0x2C)~=0x00) do
						press_for_option("up",1)
				wait_for_option_ready()
				end
				press_for_option("B",1)
				i=i-1
			end
		end
	end
end
function pause()
	emu.pause()
	while (emu.paused())do 
		emu.frameadvance()
	end
end

function stage_1()
	emu.poweron()
	emu.speedmode("turbo")
	next_para("to_next_option")
---------场景9----------
	option_view({1,1},2)
	option_view({1,2},2)
	option_view({2,1,1},1)
	option_view({2,2,1},2)
	option_view({3},1,true)
	option_view({1,1},2)
	option_view({1,2},2)
	option_view({2,1,1},2)
	option_view({2,2},2)
	option_view({3},2,true)
	option_view({3,1},1,true)
---------场景C---------
	option_view({1,1},2)
	option_view({1,2},3)
	option_view({2,1,1},4)
	option_view({2,1,2},2)
	option_view({3},1,true)
---------场景D---------
	option_view({3,3},1,true)
---------场景E---------
	option_view({1,1},2)
	option_view({1,2},1)
	option_view({2,1},1)
	option_view({2,1,1},2)
	option_view({2,1,2},1,true)
	press_for_option("down",1)
	press_for_option("A",1)
	next_para("to_next_option")
	
	option_view({1,1},1)
	option_view({2,1},1)
	option_view({2,2},1)
	option_view({1,2},1,true)
	
	press_for_option("down",1)	--这里的选项识别失效
	press_for_option("A",1)
	next_para("to_next_option")
	press_for_option("down",1)
	press_for_option("A",1)
	next_para("to_next_option")
	press_for_option("A",1)
	next_para("to_next_option")
	
--上飞机---
	option_view({1,1},2)
	option_view({1,2},1)
	option_view({1,3},1)
	option_view({2,1},1)
	option_view({2,2},1)	
	press_for_option("down",3)	--有时这种不能按一下就立马出现选项的需要这么操作
	press_for_option("A",1)
	next_para(1)
	wait_for_option_ready()
	press_for_option("A",1)
	wait_for_option_ready()
	option_view({3},1,true)
	
end

function stage_2_1()
--来到太空
	press_for_option("A",1)
	next_para(2)
	option_view({1},1)
	option_view({2,1},2)
	option_view({3,1},1,true)
--moonface
	option_view({1,1},1)
	option_view({2,1},1,true)
--进入moonface
	option_view({1,1},1)
	option_view({2,1},1)
	option_view({2,2},1)
	option_view({3,1},1,true)
---进入驾驶舱
	option_view({1,1},6)
	option_view({1,2},1)
	option_view({2},1,true)
--出来
	option_view({1,1},1)
	option_view({1,2},1)
--返回561
	option_view({2,2},1,true)
--station bay
	option_view({1,1},1,true)
	press_for_option("A",1)	--这里的选项识别失效
	next_para("to_next_option")
	option_view({1,1},1)
	option_view({2,1},1,true)
--data room
	option_view({1,1},1)
	option_view({1,2},1)
	option_view({2,1},1)
	option_view({2,2},1,ture)
--来到前台
	option_view({1,1},1)
	option_view({1,2},1)
	option_view({2,1},1)

	press_for_option("down",1)
	press_for_option("A",1)
	press_for_option("down",1)
	press_for_option("A",1)	
	next_para(1)
	wrong_input_for_VMH()
	wrong_input_for_VMH()
	wrong_input_for_VMH()
	next_para("to_next_option")
--来到561
	option_view({1,1},1)
	option_view({1,2},1)
	option_view({2,1},1,true)
--来到moonface
	option_view({1,1},1)
	option_view({2,1},1)
	option_view({2,2},1,true)
--到副层

	option_view({2,1},1)
	option_view({2,2},1,true)
--main floor
	option_view({1,1},1)
	option_view({2,1},1)
	option_view({2,2},1,true)
--sub floor
	option_view({1,1},1)
	option_view({2,1},1)
	option_view({2,3},1)
	option_view({2,1},1)
	option_view({2,2},2)
	option_view({1,1},2)		--找到梓
	option_view({1,1},1)	
	option_view({1,1},4)
--data office
	option_view({1,1},1)
	option_view({1,2},2)
	option_view({2,1},2)
	option_view({2,2},1)
	option_view({2,3},1)
	option_view({1,1},1)
	option_view({1,2},1)
--mechanic
	option_view({1,1},2)
	option_view({1,2},1)
	option_view({1,3},1)
	option_view({2,1},1)
	option_view({2,2},1)
	option_view({1,1},2,true)
--data office
	option_view({1,1},1)
	option_view({1,2},1,true)
	option_view({1,1},1,true)
	option_view({2},2)
	option_view({1},2)
	option_view({3},1,true)
	option_view({1,2},1,true)
--mechanic
	option_view({1,1},2)
	option_view({1,2},2)
	option_view({2},1)
	option_view({3},1,true)
	option_view({1,3},1,true)
--上船
	option_view({1},1)
	press_for_option("down",2)
	press_for_option("A",1)
	next_para(1)
	wait_for_option_ready()
	press_for_option("A",1)
	wait_for_option_ready()
	option_view({2,1},1,true)
	option_view({1,1},1)
	option_view({1,2},1)
	option_view({1,3},1,true)
--来到居民区
	option_view({1,1},1)
	option_view({2,1},1,true)
--中央
	option_view({1,1},1)
	option_view({1,2},1)
	option_view({2,1},1)
	option_view({2,2},1)
	option_view({3},1,true)

	option_view({1,1},1)
	option_view({1,2},1)
	option_view({2,1},1)
	option_view({2,2},1)

	press_for_option("down",1)
	press_for_option("A",1)
	press_for_option("down",1)
	press_for_option("A",1)
	next_para(12)
--希尔姬奴
	option_view({1,1},3)
	option_view({2,1},5)
	option_view({2,2},1)
	option_view({2,3},4)
	option_view({3},2)
	option_view({2,3},1,true)

	option_view({1,1},1,true)
	option_view({1,1},1)
	option_view({2},1,true)
	option_view({1,1,1},1)
	option_view({1,1,2},2)
	option_view({2},2)
	option_view({3},1,true)
	option_view({1,2},1,true)

	press_for_option("down",1)
	press_for_option("A",1)
	next_para(1)
	wait_for_option_ready()
	press_for_option("A",1)
	next_para(1)
	option_view({1,1},1,true)
	wait_for_option_ready()
	press_for_option("A",1)
	next_para("to_next_option")
--回到bay
	option_view({1,1},1)
	option_view({2,1},1,true)
	option_view({1},1)
	option_view({2},1)
	option_view({3},1,true)
	press_for_option("down",1)
	press_for_option("A",1)
	next_para("to_next_option")
	press_for_option("A",1)
	next_para(15)
	option_view({1,2},1)
	option_view({1,1},4)
	option_view({1,1},1,true)
	option_view({1,2},3,true)
	option_view({1,1},2)
	option_view({1,2},1,true)
	option_view({1,1},1)
	option_view({1,2},1)
	option_view({1,3},1)
	option_view({1,4},1)
	option_view({2},1,true)
	option_view({1,3},1,true)
	option_view({1,1},1,true)

	press_for_option("down",1)	--有时这种不能按一下就立马出现选项的需要这么操作
	press_for_option("A",1)
	next_para(1)
	wait_for_option_ready()
	press_for_option("A",1)
	wait_for_option_ready()
	option_view({1,1},1,true)

end

function stage_2_2()
	option_view({1,1},1)
	option_view({2,1},1,true)

	option_view({1,1},2)
	option_view({2,1},1)
	option_view({2,2},1)
	option_view({3,1},1,true)

	option_view({1,1},1)
	option_view({1,2},2)
	option_view({2,1},1)
	option_view({2,2},3)
	option_view({3},1,true)
--进餐厅

	option_view({1,1},1)
	option_view({1,2},1)
	option_view({2},1,true)

	option_view({1,2},1)
	option_view({1,1},1)
	option_view({2,1},1,true)

	option_view({1,1},1)
	press_for_option("A",1)
	press_for_option("down",1)
	press_for_option("A",1)
	next_para(3)

	press_for_option("down",1)	--有时这种不能按一下就立马出现选项的需要这么操作
	press_for_option("A",1)
	next_para(1)
	wait_for_option_ready()
	press_for_option("A",1)
	next_para(1)
	option_view({1,3},1,true)

	option_view({1,1},1,true)
	option_view({1,1},1)
	option_view({1,2},1)
	option_view({1,3,1},2)
	option_view({1,3,2},5)
	option_view({2},1,true)
	option_view({1,1},1,true)

	option_view({1,1},1)
	option_view({1,2},1)
	option_view({1,3},1)
	option_view({2},1,true)

	option_view({1,2},4)
	option_view({1,3},4)
	option_view({1,4},4)
	option_view({1,1},6)
	option_view({1,1},1,true)
	option_view({2,1},4)
	option_view({2,2},4)
	option_view({2,3},4)
	option_view({2,4},4)
	option_view({1},1,true)
--找来服务员
	option_view({1},2)
	option_view({2},2)
	option_view({3},3)
	option_view({4},3)
	option_view({3},3)
	option_view({3},1,true)

	press_for_option("A",1)	--有时这种不能按一下就立马出现选项的需要这么操作
	next_para(1)
	wait_for_option_ready()
	press_for_option("A",1)
	next_para("to_next_option")
end

function stage_3()
	option_view({1},13)
	option_view({1},1,true)
	press_for_option("down",1)
	press_for_option("A",1)
	next_para("to_next_option")
--来到浴室
	option_view({1,1},3)
	option_view({1,2},3)
	option_view({2,1},1,true)
--来到梓卧室
	option_view({1},1)
	option_view({2},1)
	option_view({3,1},1)
	option_view({4},1,true)
--出来
	option_view({1,1},4)
	option_view({2,2},1,true)
	option_view({1,1},3)
	option_view({2,3},1,true)
	option_view({1,1},3)
	option_view({2,1},1,true)
	option_view({2,2},1,true)
--到浴室
	option_view({1,1},9)
	option_view({2,1},1,true)
	option_view({1},4)
	option_view({1},1,true)
--小男孩
	option_view({1},4)
	option_view({2},4)
	option_view({3},4)
	option_view({4},4)
	press_for_option("down",4) --有时这种不能按一下就立马出现选项的需要这么操作
	press_for_option("A",1)
--怪物
	next_para(8)
	option_view({3},1,true)

	press_for_option("A",1) --有时这种不能按一下就立马出现选项的需要这么操作
	next_para(1)
	wait_for_option_ready()
	press_for_option("A",1)
	wait_for_option_ready()
end

function stage_4()
	option_view({1,1},3)
	option_view({1,2},1)
	option_view({2,1},1,true)
	press_for_option("down",1) --有时这种不能按一下就立马出现选项的需要这么操作
	press_for_option("A",1)
	next_para("to_next_option")
	press_for_option("A",1)
	next_para("to_next_option")
	press_for_option("down",1)
	press_for_option("A",1)
	next_para("to_next_option")	

	option_view({1,1},1) 	
	option_view({2},1,true)
	option_view({1,1},1) 
	option_view({1,2},1,true) 
	option_view({1},3) 
	option_view({2},1,true) 

	option_view({1,1,1},3)
	option_view({1,1,2},3)  
	option_view({1,2},3)
	next_para(2)	
	next_para("to_next_option")
	press_for_option("down",1)
	press_for_option("A",1)
	next_para("to_next_option")	
--汉堡店
	option_view({1,1},1) 
	option_view({1,2},4) 
	option_view({2},3) 
	option_view({3},1) 
	press_for_option("down",2)
	press_for_option("A",1)
	next_para(1)	
	wrong_input_for_MH()
	wrong_input_for_MH()
	wrong_input_for_MH()
	next_para(1)	
	wrong_input_for_MH()
	wrong_input_for_MH()
	wrong_input_for_MH()
	next_para("tooo_neexxt_ooooption!")	
	option_view({1,1},3) 
	option_view({4},1,true) 
	option_view({1},1) 
	option_view({2},3) 
	option_view({3},1,true) 
	option_view({1,2},1) 
	option_view({1,1},1,true) 
	option_view({1},8) 
	option_view({1},1,true) 
	press_for_option("down",1)
	press_for_option("A",1)
	next_para("借力")	
	press_for_option("A",1)
	next_para("来到店外")
	option_view({1},2) 	
	option_view({2},1) 
	option_view({1,1},2) 
	option_view({1,2},1,true) 
	press_for_option("A",1)
	next_para("和katty商量")	
	press_for_option("A",1)
	next_para("拜托katty一起去")	
	press_for_option("A",1)
	next_para("to_next_option")	
	option_view({1,1},2) 
	option_view({1,5},1) 
	option_view({1,1},1) 
	option_view({1,2,1},1) 
	option_view({1,2,2},1) 
	option_view({1,2,3},3) 
	option_view({1,5},1) 
	option_view({1,1},2) 
	option_view({1,5},1) 
	option_view({5},1) 
	option_view({5},1,true) 

	press_for_option("A",1) --有时这种不能按一下就立马出现选项的需要这么操作
	next_para(1)
	wait_for_option_ready()
	press_for_option("A",1)
	next_para("to_next_option")	

end

function stage_5()
	option_view({1},5) 
	option_view({2},1) 
	option_view({3,2},4) 
	option_view({3,1},3) 
	option_view({3,3},2) 
	option_view({1},1,true) 
	press_for_option("down",1)
	press_for_option("A",1)
	next_para("to_next_option")	
	press_for_option("A",1)
	next_para("to_next_option")	

	option_view({2},2) 
	option_view({3},2) 
	press_for_option("A",2)
	next_para(8)	
end

----------------------------------------------------------------------------------
emu.registerbefore(print_background_bank)
memory.registerexec(0xF071, print_sentence_number)
emu.registerexit(show_sentence_for_back)


--stage_1()		--如果需要自动化请取消注释
stage_2_1()
stage_2_2()
stage_3()
stage_4()
stage_5()

emu.message("lua脚本结束了")



