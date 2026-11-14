# Third-party notices / 第三方组件声明

## ASM 9.9 (BSD-3-Clause)

本仓库 `lib/*.jar` 与 `demo/libs/*.jar` 含 ASM 9.9 二进制，来源
https://asm.ow2.io/ ，许可原文 https://asm.ow2.io/license.html ：

> ASM: a very small and fast Java bytecode manipulation framework
> Copyright (c) 2000-2011 INRIA, France Telecom
> All rights reserved.
>
> Redistribution and use in source and binary forms, with or without
> modification, are permitted provided that the following conditions are met:
> 1. Redistributions of source code must retain the above copyright notice,
>    this list of conditions and the following disclaimer.
> 2. Redistributions in binary form must reproduce the above copyright notice,
>    this list of conditions and the following disclaimer in the documentation
>    and/or other materials provided with the distribution.
> 3. Neither the name of the copyright holders nor the names of its
>    contributors may be used to endorse or promote products derived from
>    this software without specific prior written permission.
>
> THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
> AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
> IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
> ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE
> LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
> CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
> SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
> INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
> CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
> ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
> POSSIBILITY OF SUCH DAMAGE.

## 未随本仓库分发的第三方材料

* **Minecraft client jar / intermediary jar / Mojang 官方 ProGuard 映射**：
  见 `data/NOTICE-mappings.md`。官方映射禁止「完整且未修改地再分发」，
  本仓库只保留聚合测量 CSV 与统计 JSON，不含任何映射表。
* **热门 Fabric mod 二进制**（Sodium / Iris / ImmediatelyFast / YACL /
  Xaero's Minimap / fabric-language-kotlin 等）：仅在本机 `/tmp` 下用于
  静态链接测量，**未复制进本仓库、未上传到任何下载通道**。其许可包含
  PolyForm-Shield-1.0.0、All-Rights-Reserved、LGPL-3.0 等，再分发需各自
  单独取得授权。`data/hotmods/` 只含测量结果（计数与符号名），不含 mod 字节码。
