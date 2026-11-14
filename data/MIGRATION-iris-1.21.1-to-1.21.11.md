# 移植工单: /tmp/mc/mods/batch/iris-1.8.14-beta.1+1.21.1-fabric.jar

| 判定 | 数量 | 占比 | 含义 |
|---|---|---|---|
| RESOLVE | 518 | 63.1% | 零改动即可在新版本运行 |
| RENAME | 2 | 0.2% | 可由 McPort 自动重映射 |
| SIGCHG | 51 | 6.2% | 需生成桥接 shim |
| MISSING | 250 | 30.5% | 需人工重写实现 |
| EXTERNAL | 6 | 0.7% | client jar 不含 / 本预言机不覆盖, 需另行验证 |

**自动修复上限 63.3% / 零改动存活 63.1%** (分母 821, 已排除 EXTERNAL)

## 需要桥接 shim(签名变了, 语义通常相近) —— 51 条

### `net/minecraft/class_290` (11)
- `net/minecraft/class_290.field_1575Lnet/minecraft/class_293;  # name kept by net/minecraft/class_290, descriptor changed`
- `net/minecraft/class_290.field_1576Lnet/minecraft/class_293;  # name kept by net/minecraft/class_290, descriptor changed`
- `net/minecraft/class_290.field_1577Lnet/minecraft/class_293;  # name kept by net/minecraft/class_290, descriptor changed`
- `net/minecraft/class_290.field_1580Lnet/minecraft/class_293;  # name kept by net/minecraft/class_290, descriptor changed`
- `net/minecraft/class_290.field_1584Lnet/minecraft/class_293;  # name kept by net/minecraft/class_290, descriptor changed`
- `net/minecraft/class_290.field_1585Lnet/minecraft/class_293;  # name kept by net/minecraft/class_290, descriptor changed`
- `net/minecraft/class_290.field_1590Lnet/minecraft/class_293;  # name kept by net/minecraft/class_290, descriptor changed`
- `net/minecraft/class_290.field_1592Lnet/minecraft/class_293;  # name kept by net/minecraft/class_290, descriptor changed`
- `net/minecraft/class_290.field_20888Lnet/minecraft/class_293;  # name kept by net/minecraft/class_290, descriptor changed`
- `net/minecraft/class_290.field_21468Lnet/minecraft/class_293;  # name kept by net/minecraft/class_290, descriptor changed`
- `net/minecraft/class_290.field_29337Lnet/minecraft/class_293;  # name kept by net/minecraft/class_290, descriptor changed`

### `net/minecraft/class_332` (5)
- `net/minecraft/class_332.method_25290(Lnet/minecraft/class_2960;IIFFIIII)V  # name kept by net/minecraft/class_332, descriptor changed`
- `net/minecraft/class_332.method_27535(Lnet/minecraft/class_327;Lnet/minecraft/class_2561;III)I  # name kept by net/minecraft/class_332, descriptor changed`
- `net/minecraft/class_332.method_35720(Lnet/minecraft/class_327;Lnet/minecraft/class_5481;III)I  # name kept by net/minecraft/class_332, descriptor changed`
- `net/minecraft/class_332.method_51448()Lnet/minecraft/class_4587;  # name kept by net/minecraft/class_332, descriptor changed`
- `net/minecraft/class_332.method_51739(Lnet/minecraft/class_1921;IIIII)V  # name kept by net/minecraft/class_332, descriptor changed`

### `net/minecraft/class_1921` (3)
- `net/minecraft/class_1921.<init>(Ljava/lang/String;Lnet/minecraft/class_293;Lnet/minecraft/class_293$class_5596;IZZLjava/lang/Runnable;Ljava/lang/Runnable;)V  # name kept by net/minecraft/class_1921, descriptor changed`
- `net/minecraft/class_1921.method_23031()Lnet/minecraft/class_293;  # name kept by net/minecraft/class_1921, descriptor changed`
- `net/minecraft/class_1921.method_23033()Lnet/minecraft/class_293$class_5596;  # name kept by net/minecraft/class_1921, descriptor changed`

### `net/minecraft/class_276` (2)
- `net/minecraft/class_276.method_30277()I  # name kept by net/minecraft/class_276, descriptor changed`
- `net/minecraft/class_276.method_30278()I  # name kept by net/minecraft/class_276, descriptor changed`

### `net/minecraft/class_437` (2)
- `net/minecraft/class_437.method_25402(DDI)Z  # name kept by net/minecraft/class_364, descriptor changed`
- `net/minecraft/class_437.method_25404(III)Z  # name kept by net/minecraft/class_364, descriptor changed`

### `net/minecraft/class_4588` (2)
- `net/minecraft/class_4588.method_22918(Lorg/joml/Matrix4f;FFF)Lnet/minecraft/class_4588;  # name kept by net/minecraft/class_4588, descriptor changed`
- `net/minecraft/class_4588.method_22920(Lnet/minecraft/class_4587$class_4665;Lnet/minecraft/class_777;[FFFFF[IIZ)V  # name kept by net/minecraft/class_4588, descriptor changed`

### `com/mojang/blaze3d/platform/TextureUtil` (1)
- `com/mojang/blaze3d/platform/TextureUtil.writeAsPNG(Ljava/nio/file/Path;Ljava/lang/String;IIII)V  # name kept by com/mojang/blaze3d/platform/TextureUtil, descriptor changed`

### `com/mojang/blaze3d/systems/RenderSystem` (1)
- `com/mojang/blaze3d/systems/RenderSystem.setProjectionMatrix(Lorg/joml/Matrix4f;Lnet/minecraft/class_8251;)V  # name kept by com/mojang/blaze3d/systems/RenderSystem, descriptor changed`

### `net/minecraft/class_1008` (1)
- `net/minecraft/class_1008.method_4227(IZ)V  # name kept by net/minecraft/class_1008, descriptor changed`

### `net/minecraft/class_1043` (1)
- `net/minecraft/class_1043.<init>(Lnet/minecraft/class_1011;)V  # name kept by net/minecraft/class_1043, descriptor changed`

### `net/minecraft/class_1058` (1)
- `net/minecraft/class_1058.<init>(Lnet/minecraft/class_2960;Lnet/minecraft/class_7764;IIII)V  # name kept by net/minecraft/class_1058, descriptor changed`

### `net/minecraft/class_1144` (1)
- `net/minecraft/class_1144.method_4873(Lnet/minecraft/class_1113;)V  # name kept by net/minecraft/class_1144, descriptor changed`

### `net/minecraft/class_156` (1)
- `net/minecraft/class_156.method_27958()Ljava/util/concurrent/ExecutorService;  # name kept by net/minecraft/class_156, descriptor changed`

### `net/minecraft/class_1928` (1)
- `net/minecraft/class_1928.<init>()V  # name kept by net/minecraft/class_1928, descriptor changed`

### `net/minecraft/class_1959` (1)
- `net/minecraft/class_1959.method_48162(Lnet/minecraft/class_2338;)Lnet/minecraft/class_1959$class_1963;  # name kept by net/minecraft/class_1959, descriptor changed`

### `net/minecraft/class_279` (1)
- `net/minecraft/class_279.method_1258(F)V  # name kept by net/minecraft/class_279, descriptor changed`

### `net/minecraft/class_287` (1)
- `net/minecraft/class_287.<init>(Lnet/minecraft/class_9799;Lnet/minecraft/class_293$class_5596;Lnet/minecraft/class_293;)V  # name kept by net/minecraft/class_287, descriptor changed`

### `net/minecraft/class_289` (1)
- `net/minecraft/class_289.method_60827(Lnet/minecraft/class_293$class_5596;Lnet/minecraft/class_293;)Lnet/minecraft/class_287;  # name kept by net/minecraft/class_289, descriptor changed`

### `net/minecraft/class_304` (1)
- `net/minecraft/class_304.<init>(Ljava/lang/String;Lnet/minecraft/class_3675$class_307;ILjava/lang/String;)V  # name kept by net/minecraft/class_304, descriptor changed`

### `net/minecraft/class_3675` (1)
- `net/minecraft/class_3675.method_15987(JI)Z  # name kept by net/minecraft/class_3675, descriptor changed`

### `net/minecraft/class_4587` (1)
- `net/minecraft/class_4587.method_22907(Lorg/joml/Quaternionf;)V  # name kept by net/minecraft/class_4587, descriptor changed`

### `net/minecraft/class_4618` (1)
- `net/minecraft/class_4618.<init>(Lnet/minecraft/class_4597$class_4598;)V  # name kept by net/minecraft/class_4618, descriptor changed`

### `net/minecraft/class_4696` (1)
- `net/minecraft/class_4696.method_23679(Lnet/minecraft/class_2680;)Lnet/minecraft/class_1921;  # name kept by net/minecraft/class_4696, descriptor changed`

### `net/minecraft/class_4725` (1)
- `net/minecraft/class_4725.method_24102([Lnet/minecraft/class_1011;I)[Lnet/minecraft/class_1011;  # name kept by net/minecraft/class_4725, descriptor changed`

### `net/minecraft/class_5944` (1)
- `net/minecraft/class_5944.<init>(Lnet/minecraft/class_5912;Ljava/lang/String;Lnet/minecraft/class_293;)V  # name kept by net/minecraft/class_5944, descriptor changed`

### `net/minecraft/class_7368` (1)
- `net/minecraft/class_7368.method_43041(Lnet/minecraft/class_3270;)Ljava/util/Optional;  # name kept by net/minecraft/class_7368, descriptor changed`

### `net/minecraft/class_757` (1)
- `net/minecraft/class_757.method_22973(D)Lorg/joml/Matrix4f;  # name kept by net/minecraft/class_757, descriptor changed`

### `net/minecraft/class_759` (1)
- `net/minecraft/class_759.method_22976(FLnet/minecraft/class_4587;Lnet/minecraft/class_4597$class_4598;Lnet/minecraft/class_746;I)V  # name kept by net/minecraft/class_759, descriptor changed`

### `net/minecraft/class_7764` (1)
- `net/minecraft/class_7764.<init>(Lnet/minecraft/class_2960;Lnet/minecraft/class_7771;Lnet/minecraft/class_1011;Lnet/minecraft/class_7368;)V  # name kept by net/minecraft/class_7764, descriptor changed`

### `net/minecraft/class_7922` (1)
- `net/minecraft/class_7922.method_10223(Lnet/minecraft/class_2960;)Ljava/lang/Object;  # name kept by net/minecraft/class_2378, descriptor changed`

### `net/minecraft/class_824` (1)
- `net/minecraft/class_824.method_3555(Lnet/minecraft/class_2586;FLnet/minecraft/class_4587;Lnet/minecraft/class_4597;)V  # name kept by net/minecraft/class_824, descriptor changed`

### `net/minecraft/class_8685` (1)
- `net/minecraft/class_8685.comp_1627()Lnet/minecraft/class_2960;  # name kept by net/minecraft/class_8685, descriptor changed`

## 需要重写实现(类或成员消失) —— 250 条

### `com/mojang/blaze3d/platform/GlStateManager` (44)
- `com/mojang/blaze3d/platform/GlStateManager._activeTexture(I)V  # owner class gone`
- `com/mojang/blaze3d/platform/GlStateManager._bindTexture(I)V  # owner class gone`
- `com/mojang/blaze3d/platform/GlStateManager._blendFuncSeparate(IIII)V  # owner class gone`
- `com/mojang/blaze3d/platform/GlStateManager._clearColor(FFFF)V  # owner class gone`
- `com/mojang/blaze3d/platform/GlStateManager._clear(IZ)V  # owner class gone`
- `com/mojang/blaze3d/platform/GlStateManager._colorMask(ZZZZ)V  # owner class gone`
- `com/mojang/blaze3d/platform/GlStateManager._deleteTextures([I)V  # owner class gone`
- `com/mojang/blaze3d/platform/GlStateManager._deleteTexture(I)V  # owner class gone`
- `com/mojang/blaze3d/platform/GlStateManager._depthMask(Z)V  # owner class gone`
- `com/mojang/blaze3d/platform/GlStateManager._disableBlend()V  # owner class gone`
- `com/mojang/blaze3d/platform/GlStateManager._enableBlend()V  # owner class gone`
- `com/mojang/blaze3d/platform/GlStateManager._genTextures([I)V  # owner class gone`
- `com/mojang/blaze3d/platform/GlStateManager._genTexture()I  # owner class gone`
- `com/mojang/blaze3d/platform/GlStateManager._getActiveTexture()I  # owner class gone`
- `com/mojang/blaze3d/platform/GlStateManager._getInteger(I)I  # owner class gone`
- `com/mojang/blaze3d/platform/GlStateManager._getString(I)Ljava/lang/String;  # owner class gone`
- `com/mojang/blaze3d/platform/GlStateManager._getTexLevelParameter(III)I  # owner class gone`
- `com/mojang/blaze3d/platform/GlStateManager._glBindAttribLocation(IILjava/lang/CharSequence;)V  # owner class gone`
- `com/mojang/blaze3d/platform/GlStateManager._glBindBuffer(II)V  # owner class gone`
- `com/mojang/blaze3d/platform/GlStateManager._glBindFramebuffer(II)V  # owner class gone`
- `com/mojang/blaze3d/platform/GlStateManager._glBindVertexArray(I)V  # owner class gone`
- `com/mojang/blaze3d/platform/GlStateManager._glCopyTexSubImage2D(IIIIIIII)V  # owner class gone`
- `com/mojang/blaze3d/platform/GlStateManager._glDeleteFramebuffers(I)V  # owner class gone`
- `com/mojang/blaze3d/platform/GlStateManager._glFramebufferTexture2D(IIIII)V  # owner class gone`
- `com/mojang/blaze3d/platform/GlStateManager._glGenBuffers()I  # owner class gone`
- `com/mojang/blaze3d/platform/GlStateManager._glGenVertexArrays()I  # owner class gone`
- `com/mojang/blaze3d/platform/GlStateManager._glGetUniformLocation(ILjava/lang/CharSequence;)I  # owner class gone`
- `com/mojang/blaze3d/platform/GlStateManager._glUniform1i(II)V  # owner class gone`
- `com/mojang/blaze3d/platform/GlStateManager._glUseProgram(I)V  # owner class gone`
- `com/mojang/blaze3d/platform/GlStateManager._pixelStore(II)V  # owner class gone`
- `com/mojang/blaze3d/platform/GlStateManager._viewport(IIII)V  # owner class gone`
- `com/mojang/blaze3d/platform/GlStateManager.glActiveTexture(I)V  # owner class gone`
- `com/mojang/blaze3d/platform/GlStateManager.glAttachShader(II)V  # owner class gone`
- `com/mojang/blaze3d/platform/GlStateManager.glCheckFramebufferStatus(I)I  # owner class gone`
- `com/mojang/blaze3d/platform/GlStateManager.glCompileShader(I)V  # owner class gone`
- `com/mojang/blaze3d/platform/GlStateManager.glCreateProgram()I  # owner class gone`
- `com/mojang/blaze3d/platform/GlStateManager.glCreateShader(I)I  # owner class gone`
- `com/mojang/blaze3d/platform/GlStateManager.glDeleteProgram(I)V  # owner class gone`
- `com/mojang/blaze3d/platform/GlStateManager.glDeleteShader(I)V  # owner class gone`
- `com/mojang/blaze3d/platform/GlStateManager.glGenFramebuffers()I  # owner class gone`
- `com/mojang/blaze3d/platform/GlStateManager.glGetProgrami(II)I  # owner class gone`
- `com/mojang/blaze3d/platform/GlStateManager.glGetShaderInfoLog(II)Ljava/lang/String;  # owner class gone`
- `com/mojang/blaze3d/platform/GlStateManager.glGetShaderi(II)I  # owner class gone`
- `com/mojang/blaze3d/platform/GlStateManager.glLinkProgram(I)V  # owner class gone`

### `com/mojang/blaze3d/systems/RenderSystem` (28)
- `com/mojang/blaze3d/systems/RenderSystem.activeTexture(I)V  # member gone`
- `com/mojang/blaze3d/systems/RenderSystem.applyModelViewMatrix()V  # member gone`
- `com/mojang/blaze3d/systems/RenderSystem.assertOnRenderThreadOrInit()V  # member gone`
- `com/mojang/blaze3d/systems/RenderSystem.bindTexture(I)V  # member gone`
- `com/mojang/blaze3d/systems/RenderSystem.clearColor(FFFF)V  # member gone`
- `com/mojang/blaze3d/systems/RenderSystem.clear(IZ)V  # member gone`
- `com/mojang/blaze3d/systems/RenderSystem.defaultBlendFunc()V  # member gone`
- `com/mojang/blaze3d/systems/RenderSystem.depthFunc(I)V  # member gone`
- `com/mojang/blaze3d/systems/RenderSystem.depthMask(Z)V  # member gone`
- `com/mojang/blaze3d/systems/RenderSystem.disableBlend()V  # member gone`
- `com/mojang/blaze3d/systems/RenderSystem.disableCull()V  # member gone`
- `com/mojang/blaze3d/systems/RenderSystem.disableDepthTest()V  # member gone`
- `com/mojang/blaze3d/systems/RenderSystem.enableBlend()V  # member gone`
- `com/mojang/blaze3d/systems/RenderSystem.enableCull()V  # member gone`
- `com/mojang/blaze3d/systems/RenderSystem.enableDepthTest()V  # member gone`
- `com/mojang/blaze3d/systems/RenderSystem.getProjectionMatrix()Lorg/joml/Matrix4f;  # member gone`
- `com/mojang/blaze3d/systems/RenderSystem.getShaderFogColor()[F  # member gone`
- `com/mojang/blaze3d/systems/RenderSystem.getShaderFogShape()Lnet/minecraft/class_6854;  # member gone`
- `com/mojang/blaze3d/systems/RenderSystem.getShaderTexture(I)I  # member gone`
- `com/mojang/blaze3d/systems/RenderSystem.getVertexSorting()Lnet/minecraft/class_8251;  # member gone`
- `com/mojang/blaze3d/systems/RenderSystem.glUniform1i(II)V  # member gone`
- `com/mojang/blaze3d/systems/RenderSystem.glUniformMatrix3(IZLjava/nio/FloatBuffer;)V  # member gone`
- `com/mojang/blaze3d/systems/RenderSystem.glUniformMatrix4(IZLjava/nio/FloatBuffer;)V  # member gone`
- `com/mojang/blaze3d/systems/RenderSystem.setShaderColor(FFFF)V  # member gone`
- `com/mojang/blaze3d/systems/RenderSystem.setShaderTexture(II)V  # member gone`
- `com/mojang/blaze3d/systems/RenderSystem.setShaderTexture(ILnet/minecraft/class_2960;)V  # member gone`
- `com/mojang/blaze3d/systems/RenderSystem.setShader(Ljava/util/function/Supplier;)V  # member gone`
- `com/mojang/blaze3d/systems/RenderSystem.viewport(IIII)V  # member gone`

### `net/minecraft/class_1921` (14)
- `net/minecraft/class_1921.method_23516()V  # member gone`
- `net/minecraft/class_1921.method_23518()V  # member gone`
- `net/minecraft/class_1921.method_23572(Lnet/minecraft/class_2960;)Lnet/minecraft/class_1921;  # member gone`
- `net/minecraft/class_1921.method_23577()Lnet/minecraft/class_1921;  # member gone`
- `net/minecraft/class_1921.method_23579()Lnet/minecraft/class_1921;  # member gone`
- `net/minecraft/class_1921.method_23581()Lnet/minecraft/class_1921;  # member gone`
- `net/minecraft/class_1921.method_23583()Lnet/minecraft/class_1921;  # member gone`
- `net/minecraft/class_1921.method_24049(Ljava/lang/String;Lnet/minecraft/class_293;Lnet/minecraft/class_293$class_5596;IZZLnet/minecraft/class_1921$class_4688;)Lnet/minecraft/class_1921$class_4687;  # member gone`
- `net/minecraft/class_1921.method_29997()Lnet/minecraft/class_1921;  # member gone`
- `net/minecraft/class_1921.method_34572()Lnet/minecraft/class_1921;  # member gone`
- `net/minecraft/class_1921.method_49045()Lnet/minecraft/class_1921;  # member gone`
- `net/minecraft/class_1921.method_49046()Lnet/minecraft/class_1921;  # member gone`
- `net/minecraft/class_1921.method_51785()Lnet/minecraft/class_1921;  # member gone`
- `net/minecraft/class_1921.method_61157()Lnet/minecraft/class_1921;  # member gone`

### `net/minecraft/class_296` (14)
- `net/minecraft/class_296.comp_2842()I  # owner class gone`
- `net/minecraft/class_296.comp_2843()I  # owner class gone`
- `net/minecraft/class_296.comp_2844()Lnet/minecraft/class_296$class_297;  # owner class gone`
- `net/minecraft/class_296.comp_2845()Lnet/minecraft/class_296$class_298;  # owner class gone`
- `net/minecraft/class_296.method_60843()I  # owner class gone`
- `net/minecraft/class_296.method_60844(I)Lnet/minecraft/class_296;  # owner class gone`
- `net/minecraft/class_296.method_60845(IILnet/minecraft/class_296$class_297;Lnet/minecraft/class_296$class_298;I)Lnet/minecraft/class_296;  # owner class gone`
- `net/minecraft/class_296.method_60847()I  # owner class gone`
- `net/minecraft/class_296.field_52107Lnet/minecraft/class_296;  # owner class gone`
- `net/minecraft/class_296.field_52108Lnet/minecraft/class_296;  # owner class gone`
- `net/minecraft/class_296.field_52109Lnet/minecraft/class_296;  # owner class gone`
- `net/minecraft/class_296.field_52111Lnet/minecraft/class_296;  # owner class gone`
- `net/minecraft/class_296.field_52112Lnet/minecraft/class_296;  # owner class gone`
- `net/minecraft/class_296.field_52113Lnet/minecraft/class_296;  # owner class gone`

### `net/minecraft/class_1921$class_4688$class_4689` (8)
- `net/minecraft/class_1921$class_4688$class_4689.method_23608(Lnet/minecraft/class_4668$class_4676;)Lnet/minecraft/class_1921$class_4688$class_4689;  # owner class gone`
- `net/minecraft/class_1921$class_4688$class_4689.method_23610(Lnet/minecraft/class_4668$class_4678;)Lnet/minecraft/class_1921$class_4688$class_4689;  # owner class gone`
- `net/minecraft/class_1921$class_4688$class_4689.method_23611(Lnet/minecraft/class_4668$class_4679;)Lnet/minecraft/class_1921$class_4688$class_4689;  # owner class gone`
- `net/minecraft/class_1921$class_4688$class_4689.method_23615(Lnet/minecraft/class_4668$class_4685;)Lnet/minecraft/class_1921$class_4688$class_4689;  # owner class gone`
- `net/minecraft/class_1921$class_4688$class_4689.method_23616(Lnet/minecraft/class_4668$class_4686;)Lnet/minecraft/class_1921$class_4688$class_4689;  # owner class gone`
- `net/minecraft/class_1921$class_4688$class_4689.method_23617(Z)Lnet/minecraft/class_1921$class_4688;  # owner class gone`
- `net/minecraft/class_1921$class_4688$class_4689.method_34577(Lnet/minecraft/class_4668$class_5939;)Lnet/minecraft/class_1921$class_4688$class_4689;  # owner class gone`
- `net/minecraft/class_1921$class_4688$class_4689.method_34578(Lnet/minecraft/class_4668$class_5942;)Lnet/minecraft/class_1921$class_4688$class_4689;  # owner class gone`

### `net/minecraft/class_284` (8)
- `net/minecraft/class_284.<init>(Ljava/lang/String;IILnet/minecraft/class_3679;)V  # member gone`
- `net/minecraft/class_284.method_1250(Lorg/joml/Matrix4f;)V  # member gone`
- `net/minecraft/class_284.method_1251(F)V  # member gone`
- `net/minecraft/class_284.method_1253([F)V  # member gone`
- `net/minecraft/class_284.method_1300()V  # member gone`
- `net/minecraft/class_284.method_34419(IILjava/lang/CharSequence;)V  # member gone`
- `net/minecraft/class_284.method_35649(I)V  # member gone`
- `net/minecraft/class_284.method_35664()Ljava/nio/FloatBuffer;  # member gone`

### `net/minecraft/class_291` (7)
- `net/minecraft/class_291.<init>(Lnet/minecraft/class_291$class_8555;)V  # owner class gone`
- `net/minecraft/class_291.close()V  # owner class gone`
- `net/minecraft/class_291.method_1352(Lnet/minecraft/class_9801;)V  # owner class gone`
- `net/minecraft/class_291.method_1353()V  # owner class gone`
- `net/minecraft/class_291.method_1354()V  # owner class gone`
- `net/minecraft/class_291.method_34427(Lorg/joml/Matrix4f;Lorg/joml/Matrix4f;Lnet/minecraft/class_5944;)V  # owner class gone`
- `net/minecraft/class_291.method_35665()V  # owner class gone`

### `net/minecraft/class_293` (7)
- `net/minecraft/class_293.method_1357()Ljava/util/List;  # owner class gone`
- `net/minecraft/class_293.method_1362()I  # owner class gone`
- `net/minecraft/class_293.method_22649()V  # owner class gone`
- `net/minecraft/class_293.method_22651()V  # owner class gone`
- `net/minecraft/class_293.method_34445()Ljava/util/List;  # owner class gone`
- `net/minecraft/class_293.method_60833()Lnet/minecraft/class_293$class_9803;  # owner class gone`
- `net/minecraft/class_293.method_60835(Lnet/minecraft/class_296;)I  # owner class gone`

### `net/minecraft/class_638` (7)
- `net/minecraft/class_638.method_16107()Lnet/minecraft/class_3695;  # member gone`
- `net/minecraft/class_638.method_23777(Lnet/minecraft/class_243;F)Lnet/minecraft/class_243;  # member gone`
- `net/minecraft/class_638.method_28103()Lnet/minecraft/class_5294;  # member gone`
- `net/minecraft/class_638.method_30273()I  # member gone`
- `net/minecraft/class_638.method_30274(F)F  # member gone`
- `net/minecraft/class_638.method_8442(F)F  # member gone`
- `net/minecraft/class_638.method_8510()J  # member gone`

### `net/minecraft/class_4668` (5)
- `net/minecraft/class_4668.<init>(Ljava/lang/String;Ljava/lang/Runnable;Ljava/lang/Runnable;)V  # owner class gone`
- `net/minecraft/class_4668.method_23516()V  # owner class gone`
- `net/minecraft/class_4668.method_23518()V  # owner class gone`
- `net/minecraft/class_4668.field_21346Lnet/minecraft/class_4668$class_4672;  # owner class gone`
- `net/minecraft/class_4668.field_21367Lnet/minecraft/class_4668$class_4685;  # owner class gone`

### `net/minecraft/class_5253$class_8045` (5)
- `net/minecraft/class_5253$class_8045.method_48342(I)I  # owner class gone`
- `net/minecraft/class_5253$class_8045.method_48344(IIII)I  # owner class gone`
- `net/minecraft/class_5253$class_8045.method_48345(I)I  # owner class gone`
- `net/minecraft/class_5253$class_8045.method_48346(I)I  # owner class gone`
- `net/minecraft/class_5253$class_8045.method_48347(I)I  # owner class gone`

### `net/minecraft/class_757` (5)
- `net/minecraft/class_757.method_22709(Lorg/joml/Matrix4f;)V  # member gone`
- `net/minecraft/class_757.method_34503()Lnet/minecraft/class_5944;  # member gone`
- `net/minecraft/class_757.method_34539()Lnet/minecraft/class_5944;  # member gone`
- `net/minecraft/class_757.method_34543()Lnet/minecraft/class_5944;  # member gone`
- `net/minecraft/class_757.method_34546()Lnet/minecraft/class_5944;  # member gone`

### `com/mojang/blaze3d/platform/GlStateManager$class_1017` (5)
- `com/mojang/blaze3d/platform/GlStateManager$class_1017.field_5045Lcom/mojang/blaze3d/platform/GlStateManager$class_1018;  # owner class gone`
- `com/mojang/blaze3d/platform/GlStateManager$class_1017.field_5046I  # owner class gone`
- `com/mojang/blaze3d/platform/GlStateManager$class_1017.field_5047I  # owner class gone`
- `com/mojang/blaze3d/platform/GlStateManager$class_1017.field_5048I  # owner class gone`
- `com/mojang/blaze3d/platform/GlStateManager$class_1017.field_5049I  # owner class gone`

### `net/minecraft/class_281` (4)
- `net/minecraft/class_281.method_1281(Lnet/minecraft/class_3679;)V  # owner class gone`
- `net/minecraft/class_281.method_1282()V  # owner class gone`
- `net/minecraft/class_281.method_1283(Lnet/minecraft/class_281$class_282;Ljava/lang/String;Ljava/io/InputStream;Ljava/lang/String;Lnet/minecraft/class_5913;)Lnet/minecraft/class_281;  # owner class gone`
- `net/minecraft/class_281.method_34417()I  # owner class gone`

### `net/minecraft/class_4494` (4)
- `net/minecraft/class_4494.method_22088()Ljava/lang/String;  # owner class gone`
- `net/minecraft/class_4494.method_22089()Ljava/lang/String;  # owner class gone`
- `net/minecraft/class_4494.method_22090()Ljava/lang/String;  # owner class gone`
- `net/minecraft/class_4494.method_22091()Ljava/lang/String;  # owner class gone`

### `com/mojang/blaze3d/platform/GlStateManager$class_1022` (4)
- `com/mojang/blaze3d/platform/GlStateManager$class_1022.field_5060Z  # owner class gone`
- `com/mojang/blaze3d/platform/GlStateManager$class_1022.field_5061Z  # owner class gone`
- `com/mojang/blaze3d/platform/GlStateManager$class_1022.field_5062Z  # owner class gone`
- `com/mojang/blaze3d/platform/GlStateManager$class_1022.field_5063Z  # owner class gone`

### `net/minecraft/class_296$class_297` (4)
- `net/minecraft/class_296$class_297.field_1621Lnet/minecraft/class_296$class_297;  # owner class gone`
- `net/minecraft/class_296$class_297.field_1622Lnet/minecraft/class_296$class_297;  # owner class gone`
- `net/minecraft/class_296$class_297.field_1623Lnet/minecraft/class_296$class_297;  # owner class gone`
- `net/minecraft/class_296$class_297.field_1625Lnet/minecraft/class_296$class_297;  # owner class gone`

### `net/minecraft/class_3999` (4)
- `net/minecraft/class_3999.field_17827Lnet/minecraft/class_3999;  # member gone`
- `net/minecraft/class_3999.field_17828Lnet/minecraft/class_3999;  # member gone`
- `net/minecraft/class_3999.field_17830Lnet/minecraft/class_3999;  # member gone`
- `net/minecraft/class_3999.field_17831Lnet/minecraft/class_3999;  # member gone`

### `net/minecraft/class_1044` (3)
- `net/minecraft/class_1044.method_4527(ZZ)V  # member gone`
- `net/minecraft/class_1044.method_4528()V  # member gone`
- `net/minecraft/class_1044.method_4624()I  # member gone`

### `net/minecraft/class_293$class_9803` (3)
- `net/minecraft/class_293$class_9803.method_60840()Lnet/minecraft/class_293;  # owner class gone`
- `net/minecraft/class_293$class_9803.method_60841(I)Lnet/minecraft/class_293$class_9803;  # owner class gone`
- `net/minecraft/class_293$class_9803.method_60842(Ljava/lang/String;Lnet/minecraft/class_296;)Lnet/minecraft/class_293$class_9803;  # owner class gone`

### `net/minecraft/class_5294` (3)
- `net/minecraft/class_5294.method_28108()F  # owner class gone`
- `net/minecraft/class_5294.method_28110(II)Z  # owner class gone`
- `net/minecraft/class_5294.method_29992()Lnet/minecraft/class_5294$class_5401;  # owner class gone`

### `net/minecraft/class_5944` (3)
- `net/minecraft/class_5944.method_34418()V  # member gone`
- `net/minecraft/class_5944.method_34585()V  # member gone`
- `net/minecraft/class_5944.field_29490Ljava/util/List;  # member gone`

### `net/minecraft/class_293$class_5596` (3)
- `net/minecraft/class_293$class_5596.field_27379Lnet/minecraft/class_293$class_5596;  # owner class gone`
- `net/minecraft/class_293$class_5596.field_27380Lnet/minecraft/class_293$class_5596;  # owner class gone`
- `net/minecraft/class_293$class_5596.field_27382Lnet/minecraft/class_293$class_5596;  # owner class gone`

### `com/mojang/blaze3d/platform/GlStateManager$class_1040` (2)
- `com/mojang/blaze3d/platform/GlStateManager$class_1040.method_35332()I  # owner class gone`
- `com/mojang/blaze3d/platform/GlStateManager$class_1040.method_35333()I  # owner class gone`

### `net/minecraft/class_1011` (2)
- `net/minecraft/class_1011.method_22619(IIIIIIIZZZZ)V  # member gone`
- `net/minecraft/class_1011.method_4327(IZ)V  # member gone`

### `net/minecraft/class_281$class_282` (2)
- `net/minecraft/class_281$class_282.method_1284()Ljava/lang/String;  # owner class gone`
- `net/minecraft/class_281$class_282.method_1289()Ljava/util/Map;  # owner class gone`

### `net/minecraft/class_286` (2)
- `net/minecraft/class_286.method_34420()V  # owner class gone`
- `net/minecraft/class_286.method_43433(Lnet/minecraft/class_9801;)V  # owner class gone`

### `net/minecraft/class_2874` (2)
- `net/minecraft/class_2874.comp_641()Ljava/util/OptionalLong;  # member gone`
- `net/minecraft/class_2874.comp_655()Lnet/minecraft/class_2960;  # member gone`

### `net/minecraft/class_310` (2)
- `net/minecraft/class_310.method_16011()Lnet/minecraft/class_3695;  # member gone`
- `net/minecraft/class_310.field_1703Z  # member gone`

### `net/minecraft/class_437` (2)
- `net/minecraft/class_437.method_25441()Z  # member gone`
- `net/minecraft/class_437.method_25442()Z  # member gone`

### `net/minecraft/class_7922` (2)
- `net/minecraft/class_7922.method_40266(Lnet/minecraft/class_6862;)Ljava/util/Optional;  # member gone`
- `net/minecraft/class_7922.method_40273()Ljava/util/stream/Stream;  # member gone`

### `net/minecraft/class_1079` (2)
- `net/minecraft/class_1079.field_21768Lnet/minecraft/class_1079;  # member gone`
- `net/minecraft/class_1079.field_5337Lnet/minecraft/class_1081;  # member gone`

### `net/minecraft/class_296$class_298` (2)
- `net/minecraft/class_296$class_298.field_1636Lnet/minecraft/class_296$class_298;  # owner class gone`
- `net/minecraft/class_296$class_298.field_20782Lnet/minecraft/class_296$class_298;  # owner class gone`

### `net/minecraft/class_6908` (2)
- `net/minecraft/class_6908.field_37377Lnet/minecraft/class_6862;  # member gone`
- `net/minecraft/class_6908.field_37378Lnet/minecraft/class_6862;  # member gone`

### `com/mojang/blaze3d/platform/TextureUtil` (1)
- `com/mojang/blaze3d/platform/TextureUtil.prepareImage(IIII)V  # member gone`

### `net/minecraft/class_1043` (1)
- `net/minecraft/class_1043.method_4624()I  # member gone`

### `net/minecraft/class_1047` (1)
- `net/minecraft/class_1047.method_4540()Lnet/minecraft/class_1043;  # member gone`

### `net/minecraft/class_1049` (1)
- `net/minecraft/class_1049.method_4625(Lnet/minecraft/class_3300;)V  # member gone`

### `net/minecraft/class_1058$class_7770` (1)
- `net/minecraft/class_1058$class_7770.method_45853()V  # owner class gone`

### `net/minecraft/class_1297` (1)
- `net/minecraft/class_1297.method_19538()Lnet/minecraft/class_243;  # member gone`

### `net/minecraft/class_1921$class_4688` (1)
- `net/minecraft/class_1921$class_4688.method_23598()Lnet/minecraft/class_1921$class_4688$class_4689;  # owner class gone`

### `net/minecraft/class_1937` (1)
- `net/minecraft/class_1937.method_8315()I  # member gone`

### `net/minecraft/class_2558` (1)
- `net/minecraft/class_2558.<init>(Lnet/minecraft/class_2558$class_2559;Ljava/lang/String;)V  # member gone`

### `net/minecraft/class_2568` (1)
- `net/minecraft/class_2568.<init>(Lnet/minecraft/class_2568$class_5247;Ljava/lang/Object;)V  # member gone`

### `net/minecraft/class_276` (1)
- `net/minecraft/class_276.method_1235(Z)V  # member gone`

### `net/minecraft/class_279` (1)
- `net/minecraft/class_279.method_57799(Ljava/lang/String;F)V  # member gone`

### `net/minecraft/class_285` (1)
- `net/minecraft/class_285.method_22094(I)V  # owner class gone`

### `net/minecraft/class_315` (1)
- `net/minecraft/class_315.method_42534()Lnet/minecraft/class_7172;  # member gone`

### `net/minecraft/class_332` (1)
- `net/minecraft/class_332.method_51422(FFFF)V  # member gone`

### `net/minecraft/class_4184` (1)
- `net/minecraft/class_4184.method_19326()Lnet/minecraft/class_243;  # member gone`

### `net/minecraft/class_4597` (1)
- `net/minecraft/class_4597.getBuffer(Lnet/minecraft/class_1921;)Lnet/minecraft/class_4588;  # member gone`

### `net/minecraft/class_4668$class_4683` (1)
- `net/minecraft/class_4668$class_4683.<init>(Lnet/minecraft/class_2960;ZZ)V  # owner class gone`

### `net/minecraft/class_4668$class_5942` (1)
- `net/minecraft/class_4668$class_5942.<init>(Ljava/util/function/Supplier;)V  # owner class gone`

### `net/minecraft/class_4968` (1)
- `net/minecraft/class_4968.method_26101()I  # member gone`

### `net/minecraft/class_5489` (1)
- `net/minecraft/class_5489.method_30889(Lnet/minecraft/class_332;IIII)V  # member gone`

### `net/minecraft/class_6489` (1)
- `net/minecraft/class_6489.method_48019()Ljava/lang/String;  # member gone`

### `net/minecraft/class_702` (1)
- `net/minecraft/class_702.method_3049(Lnet/minecraft/class_765;Lnet/minecraft/class_4184;F)V  # member gone`

### `net/minecraft/class_742` (1)
- `net/minecraft/class_742.method_7348(Lnet/minecraft/class_1664;)Z  # member gone`

### `net/minecraft/class_746` (1)
- `net/minecraft/class_746.method_37908()Lnet/minecraft/class_1937;  # member gone`

### `net/minecraft/class_765` (1)
- `net/minecraft/class_765.method_3316()V  # member gone`

### `net/minecraft/class_8053` (1)
- `net/minecraft/class_8053.method_48431()Lnet/minecraft/class_6880;  # member gone`

### `net/minecraft/class_8054` (1)
- `net/minecraft/class_8054.comp_1208()Ljava/lang/String;  # member gone`

### `net/minecraft/class_846$class_849` (1)
- `net/minecraft/class_846$class_849.method_3642()Ljava/util/List;  # owner class gone`

### `net/minecraft/class_846$class_851` (1)
- `net/minecraft/class_846$class_851.method_3677()Lnet/minecraft/class_846$class_849;  # member gone`

### `net/minecraft/class_9323` (1)
- `net/minecraft/class_9323.method_57829(Lnet/minecraft/class_9331;)Ljava/lang/Object;  # member gone`

### `com/mojang/blaze3d/platform/GlStateManager$class_1026` (1)
- `com/mojang/blaze3d/platform/GlStateManager$class_1026.field_5076Z  # owner class gone`

### `com/mojang/blaze3d/platform/GlStateManager$class_1039` (1)
- `com/mojang/blaze3d/platform/GlStateManager$class_1039.field_5167I  # owner class gone`

### `net/minecraft/class_291$class_8555` (1)
- `net/minecraft/class_291$class_8555.field_44793Lnet/minecraft/class_291$class_8555;  # owner class gone`

### `net/minecraft/class_5294$class_5401` (1)
- `net/minecraft/class_5294$class_5401.field_25640Lnet/minecraft/class_5294$class_5401;  # owner class gone`

### `net/minecraft/class_6854` (1)
- `net/minecraft/class_6854.field_36351Lnet/minecraft/class_6854;  # owner class gone`

