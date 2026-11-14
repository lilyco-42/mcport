# 移植工单: /tmp/mc/mods/batch/sodium-mc1.21.1-0.8.13-fabric.jar

| 判定 | 数量 | 占比 | 含义 |
|---|---|---|---|
| RESOLVE | 521 | 76.2% | 零改动即可在新版本运行 |
| RENAME | 5 | 0.7% | 可由 McPort 自动重映射 |
| SIGCHG | 47 | 6.9% | 需生成桥接 shim |
| MISSING | 111 | 16.2% | 需人工重写实现 |
| EXTERNAL | 12 | 1.8% | client jar 不含 / 本预言机不覆盖, 需另行验证 |

**自动修复上限 76.9% / 零改动存活 76.2%** (分母 684, 已排除 EXTERNAL)

## 需要桥接 shim(签名变了, 语义通常相近) —— 47 条

### `net/minecraft/class_332` (8)
- `net/minecraft/class_332.<init>(Lnet/minecraft/class_310;Lnet/minecraft/class_4597$class_4598;)V  # name kept by net/minecraft/class_332, descriptor changed`
- `net/minecraft/class_332.method_25290(Lnet/minecraft/class_2960;IIFFIIII)V  # name kept by net/minecraft/class_332, descriptor changed`
- `net/minecraft/class_332.method_25293(Lnet/minecraft/class_2960;IIIIFFIIII)V  # name kept by net/minecraft/class_332, descriptor changed`
- `net/minecraft/class_332.method_25303(Lnet/minecraft/class_327;Ljava/lang/String;III)I  # name kept by net/minecraft/class_332, descriptor changed`
- `net/minecraft/class_332.method_27535(Lnet/minecraft/class_327;Lnet/minecraft/class_2561;III)I  # name kept by net/minecraft/class_332, descriptor changed`
- `net/minecraft/class_332.method_35720(Lnet/minecraft/class_327;Lnet/minecraft/class_5481;III)I  # name kept by net/minecraft/class_332, descriptor changed`
- `net/minecraft/class_332.method_51430(Lnet/minecraft/class_327;Lnet/minecraft/class_5481;IIIZ)I  # name kept by net/minecraft/class_332, descriptor changed`
- `net/minecraft/class_332.method_51448()Lnet/minecraft/class_4587;  # name kept by net/minecraft/class_332, descriptor changed`

### `net/minecraft/class_290` (6)
- `net/minecraft/class_290.field_1576Lnet/minecraft/class_293;  # name kept by net/minecraft/class_290, descriptor changed`
- `net/minecraft/class_290.field_1580Lnet/minecraft/class_293;  # name kept by net/minecraft/class_290, descriptor changed`
- `net/minecraft/class_290.field_1584Lnet/minecraft/class_293;  # name kept by net/minecraft/class_290, descriptor changed`
- `net/minecraft/class_290.field_1590Lnet/minecraft/class_293;  # name kept by net/minecraft/class_290, descriptor changed`
- `net/minecraft/class_290.field_20888Lnet/minecraft/class_293;  # name kept by net/minecraft/class_290, descriptor changed`
- `net/minecraft/class_290.field_29337Lnet/minecraft/class_293;  # name kept by net/minecraft/class_290, descriptor changed`

### `net/minecraft/class_2680` (5)
- `net/minecraft/class_2680.method_26173(Lnet/minecraft/class_1922;Lnet/minecraft/class_2338;Lnet/minecraft/class_2350;)Lnet/minecraft/class_265;  # name kept by net/minecraft/class_4970$class_4971, descriptor changed`
- `net/minecraft/class_2680.method_26193(Lnet/minecraft/class_1922;Lnet/minecraft/class_2338;)I  # name kept by net/minecraft/class_4970$class_4971, descriptor changed`
- `net/minecraft/class_2680.method_26201(Lnet/minecraft/class_1922;Lnet/minecraft/class_2338;)Lnet/minecraft/class_265;  # name kept by net/minecraft/class_4970$class_4971, descriptor changed`
- `net/minecraft/class_2680.method_26216(Lnet/minecraft/class_1922;Lnet/minecraft/class_2338;)Z  # name kept by net/minecraft/class_4970$class_4971, descriptor changed`
- `net/minecraft/class_2680.method_26226(Lnet/minecraft/class_1922;Lnet/minecraft/class_2338;)Lnet/minecraft/class_243;  # name kept by net/minecraft/class_4970$class_4971, descriptor changed`

### `net/minecraft/class_437` (3)
- `net/minecraft/class_437.method_16803(III)Z  # name kept by net/minecraft/class_364, descriptor changed`
- `net/minecraft/class_437.method_25402(DDI)Z  # name kept by net/minecraft/class_364, descriptor changed`
- `net/minecraft/class_437.method_25404(III)Z  # name kept by net/minecraft/class_364, descriptor changed`

### `net/minecraft/class_9801$class_4574` (3)
- `net/minecraft/class_9801$class_4574.comp_749()Lnet/minecraft/class_293;  # name kept by net/minecraft/class_9801$class_4574, descriptor changed`
- `net/minecraft/class_9801$class_4574.comp_752()Lnet/minecraft/class_293$class_5596;  # name kept by net/minecraft/class_9801$class_4574, descriptor changed`
- `net/minecraft/class_9801$class_4574.comp_753()Lnet/minecraft/class_293$class_5595;  # name kept by net/minecraft/class_9801$class_4574, descriptor changed`

### `net/minecraft/class_3532` (2)
- `net/minecraft/class_3532.method_15362(F)F  # name kept by net/minecraft/class_3532, descriptor changed`
- `net/minecraft/class_3532.method_15374(F)F  # name kept by net/minecraft/class_3532, descriptor changed`

### `net/minecraft/class_4184` (2)
- `net/minecraft/class_4184.method_19336()Lorg/joml/Vector3f;  # name kept by net/minecraft/class_4184, descriptor changed`
- `net/minecraft/class_4184.method_35689()Lorg/joml/Vector3f;  # name kept by net/minecraft/class_4184, descriptor changed`

### `net/minecraft/class_4696` (2)
- `net/minecraft/class_4696.method_23679(Lnet/minecraft/class_2680;)Lnet/minecraft/class_1921;  # name kept by net/minecraft/class_4696, descriptor changed`
- `net/minecraft/class_4696.method_23680(Lnet/minecraft/class_3610;)Lnet/minecraft/class_1921;  # name kept by net/minecraft/class_4696, descriptor changed`

### `net/minecraft/class_1041` (1)
- `net/minecraft/class_1041.method_4495()D  # name kept by net/minecraft/class_1041, descriptor changed`

### `net/minecraft/class_1144` (1)
- `net/minecraft/class_1144.method_4873(Lnet/minecraft/class_1113;)V  # name kept by net/minecraft/class_1144, descriptor changed`

### `net/minecraft/class_2583` (1)
- `net/minecraft/class_2583.method_27704(Lnet/minecraft/class_2960;)Lnet/minecraft/class_2583;  # name kept by net/minecraft/class_2583, descriptor changed`

### `net/minecraft/class_2841` (1)
- `net/minecraft/class_2841.<init>(Lnet/minecraft/class_2359;Ljava/lang/Object;Lnet/minecraft/class_2841$class_6563;)V  # name kept by net/minecraft/class_2841, descriptor changed`

### `net/minecraft/class_289` (1)
- `net/minecraft/class_289.method_60827(Lnet/minecraft/class_293$class_5596;Lnet/minecraft/class_293;)Lnet/minecraft/class_287;  # name kept by net/minecraft/class_289, descriptor changed`

### `net/minecraft/class_3262` (1)
- `net/minecraft/class_3262.method_14407(Lnet/minecraft/class_3270;)Ljava/lang/Object;  # name kept by net/minecraft/class_3262, descriptor changed`

### `net/minecraft/class_342` (1)
- `net/minecraft/class_342.method_25400(CI)Z  # name kept by net/minecraft/class_364, descriptor changed`

### `net/minecraft/class_364` (1)
- `net/minecraft/class_364.method_25404(III)Z  # name kept by net/minecraft/class_364, descriptor changed`

### `net/minecraft/class_3940` (1)
- `net/minecraft/class_3940.method_3074(Lnet/minecraft/class_4588;Lnet/minecraft/class_4184;F)V  # name kept by net/minecraft/class_3940, descriptor changed`

### `net/minecraft/class_4587$class_4665` (1)
- `net/minecraft/class_4587$class_4665.<init>(Lorg/joml/Matrix4f;Lorg/joml/Matrix3f;)V  # name kept by net/minecraft/class_4587$class_4665, descriptor changed`

### `net/minecraft/class_4587` (1)
- `net/minecraft/class_4587.method_34425(Lorg/joml/Matrix4f;)V  # name kept by net/minecraft/class_4587, descriptor changed`

### `net/minecraft/class_5944` (1)
- `net/minecraft/class_5944.<init>(Lnet/minecraft/class_5912;Ljava/lang/String;Lnet/minecraft/class_293;)V  # name kept by net/minecraft/class_5944, descriptor changed`

### `net/minecraft/class_758` (1)
- `net/minecraft/class_758.method_3211(Lnet/minecraft/class_4184;Lnet/minecraft/class_758$class_4596;FZF)V  # name kept by net/minecraft/class_758, descriptor changed`

### `net/minecraft/class_761` (1)
- `net/minecraft/class_761.method_23793(Lnet/minecraft/class_1920;Lnet/minecraft/class_2680;Lnet/minecraft/class_2338;)I  # name kept by net/minecraft/class_761, descriptor changed`

### `net/minecraft/class_824` (1)
- `net/minecraft/class_824.method_3555(Lnet/minecraft/class_2586;FLnet/minecraft/class_4587;Lnet/minecraft/class_4597;)V  # name kept by net/minecraft/class_824, descriptor changed`

### `net/minecraft/class_827` (1)
- `net/minecraft/class_827.method_3563(Lnet/minecraft/class_2586;)Z  # name kept by net/minecraft/class_827, descriptor changed`

## 需要重写实现(类或成员消失) —— 111 条

### `com/mojang/blaze3d/systems/RenderSystem` (18)
- `com/mojang/blaze3d/systems/RenderSystem.blendFuncSeparate(Lcom/mojang/blaze3d/platform/GlStateManager$class_4535;Lcom/mojang/blaze3d/platform/GlStateManager$class_4534;Lcom/mojang/blaze3d/platform/GlStateManager$class_4535;Lcom/mojang/blaze3d/platform/GlStateManager$class_4534;)V  # member gone`
- `com/mojang/blaze3d/systems/RenderSystem.defaultBlendFunc()V  # member gone`
- `com/mojang/blaze3d/systems/RenderSystem.depthFunc(I)V  # member gone`
- `com/mojang/blaze3d/systems/RenderSystem.disableBlend()V  # member gone`
- `com/mojang/blaze3d/systems/RenderSystem.disableCull()V  # member gone`
- `com/mojang/blaze3d/systems/RenderSystem.enableBlend()V  # member gone`
- `com/mojang/blaze3d/systems/RenderSystem.enableCull()V  # member gone`
- `com/mojang/blaze3d/systems/RenderSystem.enableDepthTest()V  # member gone`
- `com/mojang/blaze3d/systems/RenderSystem.getProjectionMatrix()Lorg/joml/Matrix4f;  # member gone`
- `com/mojang/blaze3d/systems/RenderSystem.getShaderFogColor()[F  # member gone`
- `com/mojang/blaze3d/systems/RenderSystem.getShaderFogEnd()F  # member gone`
- `com/mojang/blaze3d/systems/RenderSystem.getShaderFogShape()Lnet/minecraft/class_6854;  # member gone`
- `com/mojang/blaze3d/systems/RenderSystem.getShaderFogStart()F  # member gone`
- `com/mojang/blaze3d/systems/RenderSystem.getShaderTexture(I)I  # member gone`
- `com/mojang/blaze3d/systems/RenderSystem.setShaderColor(FFFF)V  # member gone`
- `com/mojang/blaze3d/systems/RenderSystem.setShaderFogEnd(F)V  # member gone`
- `com/mojang/blaze3d/systems/RenderSystem.setShaderFogShape(Lnet/minecraft/class_6854;)V  # member gone`
- `com/mojang/blaze3d/systems/RenderSystem.setShaderFogStart(F)V  # member gone`

### `net/minecraft/class_1921` (8)
- `net/minecraft/class_1921.method_23516()V  # member gone`
- `net/minecraft/class_1921.method_23518()V  # member gone`
- `net/minecraft/class_1921.method_23577()Lnet/minecraft/class_1921;  # member gone`
- `net/minecraft/class_1921.method_23579()Lnet/minecraft/class_1921;  # member gone`
- `net/minecraft/class_1921.method_23581()Lnet/minecraft/class_1921;  # member gone`
- `net/minecraft/class_1921.method_23583()Lnet/minecraft/class_1921;  # member gone`
- `net/minecraft/class_1921.method_29997()Lnet/minecraft/class_1921;  # member gone`
- `net/minecraft/class_1921.method_51784()Lnet/minecraft/class_1921;  # member gone`

### `net/minecraft/class_291` (6)
- `net/minecraft/class_291.<init>(Lnet/minecraft/class_291$class_8555;)V  # owner class gone`
- `net/minecraft/class_291.close()V  # owner class gone`
- `net/minecraft/class_291.method_1352(Lnet/minecraft/class_9801;)V  # owner class gone`
- `net/minecraft/class_291.method_1353()V  # owner class gone`
- `net/minecraft/class_291.method_1354()V  # owner class gone`
- `net/minecraft/class_291.method_34427(Lorg/joml/Matrix4f;Lorg/joml/Matrix4f;Lnet/minecraft/class_5944;)V  # owner class gone`

### `net/minecraft/class_296` (6)
- `net/minecraft/class_296.method_60844(I)Lnet/minecraft/class_296;  # owner class gone`
- `net/minecraft/class_296.method_60847()I  # owner class gone`
- `net/minecraft/class_296.field_52107Lnet/minecraft/class_296;  # owner class gone`
- `net/minecraft/class_296.field_52108Lnet/minecraft/class_296;  # owner class gone`
- `net/minecraft/class_296.field_52109Lnet/minecraft/class_296;  # owner class gone`
- `net/minecraft/class_296.field_52113Lnet/minecraft/class_296;  # owner class gone`

### `net/minecraft/class_5253$class_8045` (5)
- `net/minecraft/class_5253$class_8045.method_48342(I)I  # owner class gone`
- `net/minecraft/class_5253$class_8045.method_48344(IIII)I  # owner class gone`
- `net/minecraft/class_5253$class_8045.method_48345(I)I  # owner class gone`
- `net/minecraft/class_5253$class_8045.method_48346(I)I  # owner class gone`
- `net/minecraft/class_5253$class_8045.method_48347(I)I  # owner class gone`

### `com/mojang/blaze3d/platform/GlStateManager` (4)
- `com/mojang/blaze3d/platform/GlStateManager._activeTexture(I)V  # owner class gone`
- `com/mojang/blaze3d/platform/GlStateManager._bindTexture(I)V  # owner class gone`
- `com/mojang/blaze3d/platform/GlStateManager.glGetProgrami(II)I  # owner class gone`
- `com/mojang/blaze3d/platform/GlStateManager.glGetShaderi(II)I  # owner class gone`

### `net/minecraft/class_2841$class_6563` (3)
- `net/minecraft/class_2841$class_6563.method_38312()I  # owner class gone`
- `net/minecraft/class_2841$class_6563.method_38313(III)I  # owner class gone`
- `net/minecraft/class_2841$class_6563.field_34569Lnet/minecraft/class_2841$class_6563;  # owner class gone`

### `net/minecraft/class_293` (3)
- `net/minecraft/class_293.method_1362()I  # owner class gone`
- `net/minecraft/class_293.method_60835(Lnet/minecraft/class_296;)I  # owner class gone`
- `net/minecraft/class_293.method_60836(Lnet/minecraft/class_296;)Z  # owner class gone`

### `net/minecraft/class_332` (3)
- `net/minecraft/class_332.method_49601(IIIII)V  # member gone`
- `net/minecraft/class_332.method_51450()Lnet/minecraft/class_4597$class_4598;  # member gone`
- `net/minecraft/class_332.method_51452()V  # member gone`

### `net/minecraft/class_3953` (3)
- `net/minecraft/class_3953.method_17676(II)Lnet/minecraft/class_2806;  # owner class gone`
- `net/minecraft/class_3953.method_17677()I  # owner class gone`
- `net/minecraft/class_3953.method_17678()I  # owner class gone`

### `net/minecraft/class_437` (3)
- `net/minecraft/class_437.method_25441()Z  # member gone`
- `net/minecraft/class_437.method_25442()Z  # member gone`
- `net/minecraft/class_437.method_25443()Z  # member gone`

### `net/minecraft/class_5294` (3)
- `net/minecraft/class_5294.method_28108()F  # owner class gone`
- `net/minecraft/class_5294.method_28110(II)Z  # owner class gone`
- `net/minecraft/class_5294.method_28112(Lnet/minecraft/class_243;F)Lnet/minecraft/class_243;  # owner class gone`

### `net/minecraft/class_638` (3)
- `net/minecraft/class_638.method_23785(F)Lnet/minecraft/class_243;  # member gone`
- `net/minecraft/class_638.method_28103()Lnet/minecraft/class_5294;  # member gone`
- `net/minecraft/class_638.method_30274(F)F  # member gone`

### `net/minecraft/class_293$class_5595` (3)
- `net/minecraft/class_293$class_5595.field_27372Lnet/minecraft/class_293$class_5595;  # owner class gone`
- `net/minecraft/class_293$class_5595.field_27373Lnet/minecraft/class_293$class_5595;  # owner class gone`
- `net/minecraft/class_293$class_5595.field_27375I  # owner class gone`

### `net/minecraft/class_1087` (2)
- `net/minecraft/class_1087.method_4707(Lnet/minecraft/class_2680;Lnet/minecraft/class_2350;Lnet/minecraft/class_5819;)Ljava/util/List;  # member gone`
- `net/minecraft/class_1087.method_4708()Z  # member gone`

### `net/minecraft/class_1959` (2)
- `net/minecraft/class_1959.method_24376()I  # member gone`
- `net/minecraft/class_1959.method_8697()I  # member gone`

### `net/minecraft/class_276` (2)
- `net/minecraft/class_276.method_1230(Z)V  # member gone`
- `net/minecraft/class_276.method_1235(Z)V  # member gone`

### `net/minecraft/class_310` (2)
- `net/minecraft/class_310.method_16011()Lnet/minecraft/class_3695;  # member gone`
- `net/minecraft/class_310.field_1703Z  # member gone`

### `net/minecraft/class_4763` (2)
- `net/minecraft/class_4763.method_30811()Ljava/util/Optional;  # member gone`
- `net/minecraft/class_4763.method_30812()Ljava/util/Optional;  # member gone`

### `net/minecraft/class_777` (2)
- `net/minecraft/class_777.method_3357()[I  # member gone`
- `net/minecraft/class_777.method_3359()I  # member gone`

### `com/mojang/blaze3d/platform/GlStateManager$class_4535` (2)
- `com/mojang/blaze3d/platform/GlStateManager$class_4535.ONELcom/mojang/blaze3d/platform/GlStateManager$class_4535;  # owner class gone`
- `com/mojang/blaze3d/platform/GlStateManager$class_4535.SRC_ALPHALcom/mojang/blaze3d/platform/GlStateManager$class_4535;  # owner class gone`

### `net/minecraft/class_1058` (1)
- `net/minecraft/class_1058.method_23842()F  # member gone`

### `net/minecraft/class_1092` (1)
- `net/minecraft/class_1092.method_24153(Lnet/minecraft/class_2960;)Lnet/minecraft/class_1059;  # member gone`

### `net/minecraft/class_1297` (1)
- `net/minecraft/class_1297.method_5830()Lnet/minecraft/class_238;  # member gone`

### `net/minecraft/class_1926` (1)
- `net/minecraft/class_1926.method_8341()I  # member gone`

### `net/minecraft/class_2378` (1)
- `net/minecraft/class_2378.method_40290(Lnet/minecraft/class_5321;)Lnet/minecraft/class_6880$class_6883;  # member gone`

### `net/minecraft/class_243` (1)
- `net/minecraft/class_243.method_24457(I)Lnet/minecraft/class_243;  # member gone`

### `net/minecraft/class_2586` (1)
- `net/minecraft/class_2586.getRenderData()Ljava/lang/Object;  # member gone`

### `net/minecraft/class_284` (1)
- `net/minecraft/class_284.method_22096(ILjava/lang/CharSequence;)I  # member gone`

### `net/minecraft/class_286` (1)
- `net/minecraft/class_286.method_34420()V  # owner class gone`

### `net/minecraft/class_315` (1)
- `net/minecraft/class_315.method_42534()Lnet/minecraft/class_7172;  # member gone`

### `net/minecraft/class_325` (1)
- `net/minecraft/class_325.method_1704(Lnet/minecraft/class_1799;I)I  # owner class gone`

### `net/minecraft/class_4184` (1)
- `net/minecraft/class_4184.method_19326()Lnet/minecraft/class_243;  # member gone`

### `net/minecraft/class_4597$class_4598` (1)
- `net/minecraft/class_4597$class_4598.getBuffer(Lnet/minecraft/class_1921;)Lnet/minecraft/class_4588;  # member gone`

### `net/minecraft/class_4722` (1)
- `net/minecraft/class_4722.method_24076()Lnet/minecraft/class_1921;  # member gone`

### `net/minecraft/class_5407` (1)
- `net/minecraft/class_5407.method_30142()Z  # member gone`

### `net/minecraft/class_6007` (1)
- `net/minecraft/class_6007.method_34976()I  # owner class gone`

### `net/minecraft/class_6008$class_6010` (1)
- `net/minecraft/class_6008$class_6010.comp_2542()Ljava/lang/Object;  # owner class gone`

### `net/minecraft/class_6008` (1)
- `net/minecraft/class_6008.method_34979()Lnet/minecraft/class_6007;  # owner class gone`

### `net/minecraft/class_6854` (1)
- `net/minecraft/class_6854.method_40036()I  # owner class gone`

### `net/minecraft/class_7677` (1)
- `net/minecraft/class_7677.method_45252(Ljava/lang/String;Lcom/mojang/serialization/Codec;)Lnet/minecraft/class_7677;  # member gone`

### `net/minecraft/class_8494` (1)
- `net/minecraft/class_8494.method_51255(I)Z  # owner class gone`

### `net/minecraft/class_918` (1)
- `net/minecraft/class_918.method_29711(Lnet/minecraft/class_4597;Lnet/minecraft/class_1921;ZZ)Lnet/minecraft/class_4588;  # member gone`

### `com/mojang/blaze3d/platform/GlStateManager$class_4534` (1)
- `com/mojang/blaze3d/platform/GlStateManager$class_4534.ONE_MINUS_SRC_ALPHALcom/mojang/blaze3d/platform/GlStateManager$class_4534;  # owner class gone`

### `net/minecraft/class_291$class_8555` (1)
- `net/minecraft/class_291$class_8555.field_44794Lnet/minecraft/class_291$class_8555;  # owner class gone`

### `net/minecraft/class_293$class_5596` (1)
- `net/minecraft/class_293$class_5596.field_27382Lnet/minecraft/class_293$class_5596;  # owner class gone`

### `net/minecraft/class_758$class_4596` (1)
- `net/minecraft/class_758$class_4596.field_20946Lnet/minecraft/class_758$class_4596;  # member gone`

