# LLM / VLM / JEPA 技术面试准备路线图

> 目标：面向技术面试，系统复习 LLM、VLM、JEPA / 世界模型，重点放在应用层、工程落地、系统设计与项目讲述。默认目标岗位包括 LLM 应用工程师、AI Infra 应用侧工程师、多模态应用工程师、Agent / RAG 工程师。

---

## 第零部分：使用方式

### 面试优先级

| 优先级 | 内容 | 面试收益 |
|--------|------|----------|
| P0 | Transformer、推理优化、RAG、Agent、评估、项目讲述 | 高频必问，决定是否能过技术面 |
| P1 | VLM 架构、VLM 应用、微调、部署选型、安全 | 区分应用深度与工程经验 |
| P2 | JEPA、世界模型、前沿趋势 | 展示理论视野，通常不要求实现 |

### 建议学习顺序

1. 先掌握 LLM 基础和推理部署，能解释模型如何生成、为什么慢、如何优化。
2. 再掌握 RAG、Agent、评估和安全，能设计一个可上线的 LLM 应用系统。
3. 然后补 VLM，用多模态项目证明自己能处理图像、OCR、图表、文档等真实输入。
4. 最后学习 JEPA / 世界模型，用于回答前沿问题，不建议投入大量项目时间。

### 面试回答标准

| 题型 | 回答框架 |
|------|----------|
| 概念题 | 定义 → 为什么需要 → 怎么做 → trade-off → 工程例子 |
| 系统设计题 | 需求澄清 → 架构 → 数据流 → 关键瓶颈 → 评估指标 → 失败兜底 |
| 项目题 | 必须准备 2-3 个指标：准确率、召回率、延迟、吞吐、成本、成功率、错误率、用户反馈 |

---

## 第一部分：LLM 基础（必考）

### 1.1 Transformer 架构
- Self-Attention 机制：Q/K/V 计算、缩放点积、多头注意力
- 位置编码：绝对位置编码、RoPE、ALiBi
- Layer Norm：Pre-Norm vs Post-Norm
- FFN 层：标准 FFN、GLU 变体（SwiGLU 等）
- Encoder-Only vs Decoder-Only vs Encoder-Decoder

**面试抓手**
- 复杂度：标准 attention 时间与显存复杂度都是 O(n²)，长上下文主要瓶颈来自 attention matrix 和 KV Cache。
- Decoder-only 成为主流的原因：自回归生成简单、可扩展、适合统一文本任务。
- Pre-Norm 更适合深层网络训练稳定性，Post-Norm 在原始 Transformer 中常见但深层训练更难。

### 1.2 训练流程（背景了解）
- 预训练：next-token prediction、CLM vs MLM
- SFT（Supervised Fine-Tuning）：指令微调的目的
- RLHF / DPO / RLAIF：对齐方法的原理与区别（面试常考）
- 重点理解：训练阶段如何影响模型能力，不需要深入训练细节

### 1.3 推理优化与部署
- KV Cache：原理、内存占用分析
- 量化：INT8/INT4/GPTQ/AWQ/GGUF
- 采样策略：temperature、top-k、top-p、repetition penalty
- 投机解码（Speculative Decoding）
- Continuous Batching、PagedAttention（vLLM）

**面试抓手**
- 推理分为 prefill 和 decode 两阶段：prefill 计算密集，decode 通常受内存带宽和 KV Cache 访问限制。
- 延迟优化：减少 prompt 长度、启用 KV Cache、batching、量化、speculative decoding、选择更小模型或 MoE。
- 吞吐优化：continuous batching、PagedAttention、多 GPU 并行、请求调度、缓存复用。

### 1.3.1 主流推理框架选型

**高性能推理引擎**
- vLLM：PagedAttention、Continuous Batching，最流行，OpenAI 兼容 API
- TensorRT-LLM（NVIDIA）：极致优化，支持 FP8/INT4，适合部署
- SGLang：RadixAttention，适合复杂 LLM 程序（多轮调用、branching）
- llama.cpp / GGUF：CPU/边缘设备推理，量化支持好，轻量

**云服务 / 托管方案**
- TGI（Text Generation Inference）（HuggingFace）：生产级，支持多 GPU
- Ollama：本地一键部署，面向开发者，基于 llama.cpp
- DeepSpeed-FastGen（微软）：SplitFuse 策略

**量化 / 轻量部署**
- GPTQ / AWQ：训练后量化，配合 vLLM/TRT-LLM 使用
- GGUF：llama.cpp 生态，支持 Q4_K_M 等多种量化格式
- EXL2（ExLlamaV2）：GPTQ 的优化实现，速度更快

**多模态推理**
- vLLM：已支持部分 VLM（LLaVA、Qwen-VL 等）
- LMDeploy（上海AI Lab）：InternVL 等模型的专用推理引擎
- SGLang：也支持多模态

**选型速查**

| 场景 | 推荐 | 主要理由 |
|------|------|----------|
| 快速实验/本地开发 | Ollama、llama.cpp | 上手快、模型管理简单、低依赖 |
| 生产部署（GPU 服务器） | vLLM、TGI | OpenAI 兼容、吞吐高、生态成熟 |
| NVIDIA 显卡极致性能 | TensorRT-LLM | 深度算子优化、FP8/INT4 支持好 |
| 复杂 LLM workflow | SGLang | 适合多轮、分支、结构化推理流程 |
| 边缘/移动端 | llama.cpp、MLC-LLM | 轻量、量化格式成熟、CPU/端侧友好 |

### 1.4 长上下文与扩展
- RoPE 外推：NTK-aware、YaRN、Dynamic NTK
- Ring Attention、Flash Attention
- 上下文窗口扩展的技术路线

**面试抓手**
- 长上下文不等于有效记忆：窗口变长会带来检索困难、注意力稀释、成本上升。
- 工程上常与 RAG、摘要记忆、上下文压缩结合，而不是单纯扩大 context window。

### 1.5 关键概念
- Scaling Laws（Chinchilla、Kaplan）
- 涌现能力（Emergent Abilities）
- In-Context Learning vs Fine-Tuning
- Chain-of-Thought Prompting
- Mixture of Experts（MoE）

**容易被追问**
- In-Context Learning 是推理时从上下文中临时适配，不改变参数；Fine-Tuning 改变参数，适合稳定、重复、风格或领域任务。
- MoE 提升参数规模但每 token 只激活部分专家，难点在路由、负载均衡、通信开销和部署复杂度。

---

## 第二部分：VLM 视觉语言模型

### 2.1 视觉编码器
- ViT（Vision Transformer）：patch embedding、CLS token
- CLIP：对比学习、zero-shot 能力
- SigLIP、EVA-CLIP 等改进
- DINOv2：自监督视觉特征

### 2.2 VLM 架构范式
- Cross-Attention 融合（Flamingo 风格）
- 投影层融合（LLaVA 风格）：visual projection + token
- Q-Former（BLIP-2 风格）：learnable query 桥接
- 原生多模态（Fuyu、Chameleon 风格）

**面试抓手**
- LLaVA 风格简单高效：视觉编码器抽特征，projection 对齐到 LLM embedding space，再作为 visual tokens 输入 LLM。
- Q-Former 的价值：用少量 learnable query 从视觉特征中抽取与语言相关的信息，降低视觉 token 数量。
- 原生多模态路线更统一，但训练成本和数据要求更高。

### 2.3 主流 VLM 模型
- LLaVA 系列（1.0 → 1.5 → 1.6 → NeXT）
- Qwen-VL / Qwen2-VL / Qwen2.5-VL
- InternVL 系列
- GPT-4V / GPT-4o / Gemini / Claude 3 系列（闭源参考）

### 2.4 VLM 训练流程（背景了解）
- Stage 1：视觉-语言对齐预训练（理解目的即可）
- Stage 2：视觉指令微调（Visual Instruction Tuning）
- 重点理解：为什么需要两阶段训练，不需要深入数据构建细节

### 2.5 VLM 能力与局限
- 理解能力：描述、VQA、OCR、图表理解
- 推理能力：空间推理、计数、因果推理
- 局限：幻觉（hallucination）、空间理解弱、计数差

**工程缓解方式**
- OCR / 文档场景：将 OCR 工具结果作为结构化上下文输入，而不是完全依赖 VLM 读图。
- 图表 / 表格场景：先抽取结构化数据，再让 LLM 做解释和推理。
- 高分辨率场景：切图、dynamic resolution、局部 crop、两阶段粗到细检索。
- 幻觉缓解：强制引用区域、返回坐标、使用检测模型交叉验证、拒答不确定内容。

---

## 第三部分：JEPA 与世界模型

### 3.1 为什么需要世界模型
- LeCun 的 "AI Path" 论点
- 当前 AI 的缺陷：缺乏预测能力、无法规划
- 世界模型的定义与意义

### 3.2 JEPA 核心思想
- Joint Embedding Predictive Architecture
- 为什么在 latent space 预测而非 pixel space
- 信息瓶颈与抽象表示

**面试抓手**
- GPT 是在 token space 做自回归预测；JEPA 试图在 latent space 预测世界状态。
- Pixel-level prediction 会浪费大量容量在低层细节，latent prediction 更关注语义和可预测因素。
- JEPA 的面试价值主要是解释“为什么当前生成式模型不等于真正的世界模型”。

### 3.2.1 非对比学习详解（BYOL、VICReg、Barlow Twins）

**为什么叫"非对比"：核心区别在于 loss 是否依赖负样本**

对比学习（SimCLR、MoCo）的 loss 必须同时包含：
- 正样本对：同一图像的不同增强，拉近距离
- 负样本对：不同图像，推远距离
- InfoNCE / NT-Xent loss 本质是从一堆负样本中把正样本找出来
- **没有负样本，对比学习无法工作**——模型会坍缩（collapse），把所有输入映射到同一点

非对比方法完全不用负样本，只用正样本对，通过不同机制防止坍缩：

**BYOL（Bootstrap Your Own Latent）**
- 两个网络：Student 和 Teacher
- Student 预测 Teacher 的输出（只有"拉"，没有"推"）
- Teacher 是 Student 的 EMA（指数滑动平均）
- 防坍缩机制：Teacher 的 EMA 更新造成不对称性，Student 无法学到 trivial solution

**Barlow Twins**
- 计算两个增强视图的互相关矩阵（cross-correlation matrix）
- Loss = 让这个矩阵接近单位矩阵
  - 对角线 → 1（invariance：同一样本的增强应相似）
  - 非对角线 → 0（decorrelation：不同特征维度应独立）
- 灵感来自神经科学家 Barlow 1961 年的冗余缩减原则
- 防坍缩机制：显式的特征去相关

**VICReg（Variance-Invariance-Covariance Regularization）**
- 显式正则化三项：
  - **V**ariance：每个特征维度的方差要大（防止坍缩到常数）
  - **I**nvariance：两个增强视图的表示要相似（拉近）
  - **C**ovariance：特征间的协方差要小（去相关，防止冗余）
- 防坍缩机制：三项正则化的组合

**对比总结**

| | 对比学习 | 非对比学习 |
|---|---|---|
| 负样本 | 必须有 | 完全不需要 |
| Loss 核心 | 拉近正 + 推远负 | 只拉近正 + 防坍缩正则 |
| 坍缩防护 | 负样本的"推力" | EMA不对称 / 去相关 / 方差约束 |
| 代表方法 | SimCLR、MoCo、CLIP | BYOL、Barlow Twins、VICReg |

JEPA 选择非对比路线：不需要维护巨大的负样本库，训练更简洁，且与 prediction-based 目标更自然配合。

### 3.3 V-JEPA / VL-JEPA
- V-JEPA：视频中的时空表示学习
- VL-JEPA：视觉-语言联合嵌入
- 与 CLIP 的区别：对比 vs 预测

### 3.4 相关概念
- World Models（Ha & Schmidhuber）
- Model-Based RL vs Model-Free RL
- Dreamer / IRIS 等 world model 实践
- LeCun 的 A Path Towards Autonomous Machine Intelligence（2022）

### 3.5 JEPA vs 当前范式对比
| 维度 | VLM / LLM 自回归范式 | JEPA 预测式范式 |
|------|----------------------|------------------|
| 预测空间 | token / pixel token / multimodal token | latent representation |
| 训练目标 | next token / masked token / instruction following | 预测被 mask 或未来的 latent state |
| 优势 | 生成能力强、工程生态成熟、应用落地快 | 更接近抽象世界建模，潜在规划能力更强 |
| 局限 | 可能缺乏稳定世界状态、依赖外部搜索和 prompt | 工程生态不成熟，应用落地案例少 |
| 面试定位 | 必须能设计应用系统 | 能解释理论方向即可 |

---

## 第四部分：应用层（重点）

> 这一部分是面试主战场。不要只背概念，要能把一个 LLM 应用从需求、架构、数据、评估、部署、安全完整讲清楚。

### 4.1 Prompt Engineering 系统化
- 基础技巧：Few-shot、Zero-shot、Role-playing
- 高级技巧：Chain-of-Thought、Tree-of-Thought、Self-Consistency
- 结构化输出：JSON Mode、Function Calling、Tool Use
- Prompt 注入攻击与防御

**工程化要点**
- Prompt 要版本管理，记录变更、评估集表现和线上回归。
- 结构化输出必须做 schema validation、重试、降级和错误日志。
- 不要把安全边界只放在 prompt 里，敏感操作必须经过权限系统和后端校验。

### 4.2 RAG（Retrieval-Augmented Generation）
- 基础架构：Index → Retrieve → Generate
- 向量数据库：FAISS、Milvus、Chroma、Pinecone
- Embedding 模型选型：OpenAI、BGE、GTE、Jina
- 切分策略：固定长度、语义切分、递归切分
- 高级 RAG：Hybrid Search、Reranker、Query Rewriting、Self-RAG
- 评估指标：Faithfulness、Relevance、Context Recall

**RAG 系统设计检查点**
- 数据接入：文档解析、去重、权限、增量更新、版本管理。
- 索引构建：chunk size、overlap、metadata、embedding 模型、向量库选型。
- 检索链路：query rewrite、hybrid search、top-k、reranker、上下文压缩。
- 生成链路：引用来源、拒答策略、结构化输出、答案后处理。
- 评估链路：离线 golden set、线上反馈、bad case 分类、召回率与忠实度分开评估。

**常见失败模式**
- 检索不到：chunking 不合理、embedding 不匹配、query 表达和文档表达差异大。
- 检索到了但答错：上下文太长、rerank 不准、prompt 没要求引用、模型忽略证据。
- 答案不可用：格式不稳定、没有置信度、没有拒答、权限过滤缺失。

### 4.3 Agent 与 Tool-use
- ReAct 框架：Reasoning + Acting 交替
- Function Calling：OpenAI / Claude 实现
- 多 Agent 协作：AutoGen、CrewAI、LangGraph
- 工具调用链：路由、错误处理、重试
- 记忆机制：短期（上下文）、长期（向量存储）、工作记忆

**Agent 系统设计检查点**
- 工具定义：输入输出 schema、权限边界、幂等性、超时、重试。
- 决策控制：最大步数、循环检测、成本预算、人工确认节点。
- 状态管理：任务状态、工具结果、错误信息、可恢复 checkpoint。
- 观测性：每一步 trace、token 成本、工具耗时、失败原因分类。
- 安全：prompt injection、工具越权、数据泄露、不可逆操作审批。

### 4.4 微调与适配（应用视角）
- 全量微调 vs 参数高效微调
- LoRA / QLoRA：原理、适用场景、显存估算
- 何时微调 vs 何时 Prompt Engineering vs 何时 RAG
- 常见微调框架：LLaMA-Factory、Axolotl、Unsloth

**选择原则**
- Prompt：任务简单、变化快、数据少，优先尝试。
- RAG：答案依赖外部知识、知识频繁更新、需要引用来源。
- Fine-tuning：需要稳定格式、领域风格、特定操作模式，且有高质量训练数据。
- RLHF / DPO：更偏偏好对齐和风格优化，应用面试中通常讲原理和适用场景即可。

### 4.5 评估与监控
- 通用评估：BLEU、ROUGE、BERTScore
- LLM-as-Judge：GPT-4 评估、MT-Bench
- 任务特定评估：MMLU、HumanEval、GSM8K
- 生产监控：延迟、吞吐、成本、用户反馈

**应用评估框架**
- 离线评估：构造 golden set，覆盖正常样本、边界样本、对抗样本和真实 bad case。
- 在线评估：A/B test、用户反馈、人工抽检、问题升级率。
- 质量指标：正确性、忠实度、完整性、格式合规率、拒答准确率。
- 工程指标：P50/P95/P99 延迟、吞吐、token 成本、超时率、重试率。
- 安全指标：越狱成功率、敏感信息泄露率、危险工具调用拦截率。

### 4.6 安全与对齐（应用视角）
- 幻觉检测与缓解
- 内容安全：毒性检测、越狱防护
- 隐私：PII 脱敏、差分隐私
- 版权与合规：训练数据溯源

**面试重点**
- Prompt injection 不是 prompt 层能完全解决的问题，需要权限隔离、工具白名单、输出校验和审计日志。
- RAG 需要做权限感知检索，不能先检索所有文档再让模型自行判断能否回答。
- 幻觉缓解要结合检索证据、置信度、引用、拒答和人工兜底。

### 4.7 LLM 应用系统设计模板

| 模块 | 面试要讲清楚的问题 |
|------|--------------------|
| 入口层 | 用户是谁、输入是什么、SLA 是什么、是否需要流式输出 |
| 编排层 | 单次调用、RAG、Agent、workflow、是否需要状态机 |
| 模型层 | 闭源 API 还是开源部署、模型大小、上下文长度、成本 |
| 数据层 | 文档解析、向量库、权限、缓存、日志、反馈数据 |
| 评估层 | 离线评估集、线上指标、LLM-as-Judge、人工抽检 |
| 安全层 | PII、权限、越狱、prompt injection、工具调用审批 |
| 运维层 | 监控、trace、限流、降级、灰度发布、成本告警 |

**典型追问**
- 如果用户说答案不准，你如何定位是检索问题、模型问题还是 prompt 问题？
- 如果延迟太高，你会优先优化哪一层？
- 如果知识库每天更新，索引如何增量维护？
- 如果不同用户权限不同，RAG 如何避免越权召回？

---

## 第五部分：前沿方向

### 5.1 VLM + 规划能力
- VLM 用于机器人规划（RT-2、SayCan、VIMA）
- 视觉推理 benchmark：MMMU、MathVista、AI2D

### 5.2 多模态 Agent
- WebAgent / GUI Agent
- Embodied AI：VLM 驱动的机器人

### 5.3 前沿趋势
- Test-Time Compute / Inference-time Scaling
- Unified Multimodal Models（Chameleon、Emu）
- Video Generation as World Model（Sora 路线）

### 5.4 面试中的前沿题回答边界

- 不要把前沿概念说成已经成熟落地，要区分 research prototype 和 production system。
- 可以用“当前工程上怎么近似解决”连接前沿理论，例如用 Agent loop 近似规划、用 RAG 近似外部记忆。
- 遇到 JEPA / 世界模型问题，重点回答动机、范式差异和局限，不需要硬凑项目经验。

---

## 第六部分：面试高频问题

### LLM 基础
- [ ] Transformer 的 attention 复杂度是多少？如何优化？
- [ ] RoPE 是怎么工作的？为什么比绝对位置编码好？
- [ ] KV Cache 占用多少显存？如何估算？
- [ ] Flash Attention 的核心思想是什么？
- [ ] RLHF 和 DPO 的区别？各自优缺点？
- [ ] MoE 的路由机制和负载均衡问题

**回答检查点**
- 公式或复杂度要能写出来，但不要停在公式，要讲到工程瓶颈。
- 能区分训练优化、推理优化、部署优化，不要混在一起。

### VLM
- [ ] LLaVA 的架构是什么？为什么分两阶段训练？
- [ ] 为什么 VLM 会产生幻觉？怎么缓解？
- [ ] CLIP 的训练目标是什么？有什么局限？
- [ ] VLM 如何处理高分辨率图像？（Dynamic Resolution）
- [ ] Qwen2-VL 和 LLaVA 的架构差异

**回答检查点**
- 必须能画出“图像 → vision encoder → projector / Q-Former → LLM → text”的数据流。
- 讲局限时要给工程缓解方案，例如 OCR、检测、切图、坐标引用、人工校验。

### JEPA / 世界模型
- [ ] JEPA 和 GPT 的根本区别是什么？
- [ ] 为什么在 latent space 预测比 pixel space 好？
- [ ] LeCun 认为当前 AI 的核心缺陷是什么？
- [ ] 非对比学习和对比学习的核心区别是什么？
- [ ] BYOL 没有负样本为什么不会坍缩？

**回答检查点**
- 不要把 JEPA 讲成“更强 GPT”，它是不同预测目标和表示学习范式。
- 可以承认应用生态不成熟，这反而显得判断准确。

### 应用层（高频）
- [ ] RAG 的完整链路是什么？如何评估 RAG 系统？
- [ ] 什么时候该用 RAG，什么时候该用微调？
- [ ] LoRA 的原理是什么？为什么能节省显存？
- [ ] 如何设计一个 Agent 系统？ReAct 是什么？
- [ ] Function Calling 是怎么实现的？
- [ ] 如何缓解 LLM 幻觉？有哪些具体方法？
- [ ] vLLM 的 PagedAttention 解决了什么问题？
- [ ] 如何评估 LLM 的输出质量？
- [ ] 如何设计一个企业知识库问答系统？
- [ ] 如何设计一个可靠的 Function Calling / Tool-use 系统？
- [ ] 如何处理 prompt injection 和工具越权？
- [ ] 如何降低 LLM 应用的延迟和成本？

**回答检查点**
- 应用题一定要讲 trade-off：质量、延迟、成本、安全、可维护性。
- 系统设计题要主动补充 observability、eval、fallback，否则容易显得只会 demo。

---

## 第七部分：面试项目准备

> 面试官最看重的是能落地的能力。建议准备 2-3 个项目，覆盖以下方向。

### 第一优先级（必做）

#### 7.1 RAG 系统
- 完整链路：文档切分 + Embedding + 向量检索 + LLM 生成
- 进阶：Reranker、Hybrid Search（BM25 + 向量）
- 必须做 eval：Faithfulness、Relevance 指标
- 加分项：对比不同 chunking 策略、不同 Embedding 模型的效果

**最低可展示标准**
- 有 50-100 条自建评估问题，覆盖事实问答、跨文档问答、拒答、权限边界。
- 能展示 baseline vs 改进方案，例如 only vector search → hybrid search + reranker。
- 能解释失败样本，并给出下一步优化方向。

#### 7.2 Agent / Tool-use 系统
- 实现 ReAct 循环：LLM 决策 → 调用工具 → 观察结果 → 继续推理
- Function Calling 实战（OpenAI 或开源模型）
- 加分项：多步骤任务、错误恢复、LangGraph 实现

**最低可展示标准**
- 至少接入 3 个真实工具，例如搜索、数据库查询、代码执行、日历、工单系统。
- 有 trace 页面或日志，能复盘每一步为什么调用某个工具。
- 有最大步数、超时、重试、人工确认和失败降级。

#### 7.3 Loop Engineering（重点）
核心是让 LLM/VLM 在循环中自我修正，体现推理过程的工程化能力：

| 模式 | 核心机制 | 典型场景 |
|------|---------|---------|
| Reflexion | 执行 → 反思错误 → 重试 | 代码生成、复杂推理 |
| Self-Refine | 生成 → 自我评估 → 修正 | 文本润色、逻辑检查 |
| Tree-of-Thought | 多分支探索 → 评估 → 回溯 | 规划、博弈类问题 |
| LATS | Monte Carlo + 搜索树 | 需要深度推理的任务 |

建议项目：**Self-Debugging Code Generator**
- LLM 生成代码 → 执行 → 捕获错误 → 反馈给 LLM 修正
- 循环直到通过测试或达到上限
- 记录：成功率、平均循环次数、常见错误类型
- 面试加分：讲这个项目时可以引出 LeCun 的批评——"这种 loop 是在 token space 做搜索，不是在 latent space 做规划。但在工程上，它确实解决了大量实际问题。" 一句话同时展示工程能力和理论深度

### 第二优先级（选做其一）

#### 7.4 VLM 应用
- 基于 LLaVA/Qwen-VL 做图像理解 pipeline
- 场景：文档 OCR、图表分析、商品描述生成
- 加分项：本地部署 + 推理优化（量化、vLLM）

**最低可展示标准**
- 有真实图片集和标注样本，不只用几张 demo 图。
- 能说明 VLM、OCR、检测模型之间如何分工。
- 能用准确率、人工通过率、字段抽取 F1 或错误类型分布说明效果。

#### 7.5 模型微调实战
- LoRA 微调一个小模型（如 Qwen2-7B）
- 对比微调前后效果，做 eval
- 加分项：QLoRA 省显存、LLaMA-Factory 实操

**最低可展示标准**
- 数据来源、清洗规则、训练集 / 验证集划分讲得清楚。
- 有微调前后对比，不只展示主观样例。
- 能解释为什么不用 RAG 或 prompt 解决。

### 项目讲述框架

每个项目准备 3 个版本的叙述：
1. **30 秒版**：做什么、用了什么、效果如何
2. **2 分钟版**：架构设计、关键技术选型、踩过的坑
3. **深挖版**：为什么选这个方案、和替代方案的对比、量化指标

### 项目评分表

| 维度 | 不合格 | 合格 | 加分 |
|------|--------|------|------|
| 问题定义 | 只说做了 demo | 有明确用户和场景 | 有真实约束和业务指标 |
| 技术链路 | 只调用模型 API | 有完整数据流和模块拆分 | 有可观测性、降级和安全设计 |
| 评估 | 只展示样例 | 有离线评估集和指标 | 有 ablation、bad case 分析、线上反馈 |
| 工程质量 | 本地脚本 | 可部署、可复现 | 有监控、限流、缓存、成本优化 |
| 讲述深度 | 只背概念 | 能解释 trade-off | 能主动比较替代方案 |

### 不建议做的
- 纯 demo 级别的 chatbot（太浅）
- 没有 eval 的项目（无法证明效果）
- JEPA 相关项目（目前没有成熟开源实现，面试问到能答理论即可）

---

## 第八部分：4 周复习计划

### 第 1 周：LLM 基础与推理部署
- Day 1-2：Transformer、RoPE、KV Cache、Flash Attention
- Day 3-4：量化、vLLM、PagedAttention、推理延迟与吞吐
- Day 5-7：整理 6-8 道 LLM 高频题答案，并能手画推理链路

### 第 2 周：RAG 与应用系统设计
- Day 1-2：RAG 基础链路、chunking、embedding、向量库
- Day 3-4：hybrid search、reranker、query rewrite、权限检索
- Day 5-7：完成一个 RAG 项目 baseline 和评估集

### 第 3 周：Agent、评估、安全与微调
- Day 1-2：ReAct、Function Calling、Tool-use、LangGraph
- Day 3：LLM eval、LLM-as-Judge、线上监控
- Day 4：prompt injection、隐私、安全边界
- Day 5-7：完善 Agent 或 Loop Engineering 项目的 trace 和指标

### 第 4 周：VLM、JEPA 与面试表达
- Day 1-2：VLM 架构、LLaVA、Qwen-VL、OCR / 图表场景
- Day 3：JEPA、世界模型、非对比学习
- Day 4-5：项目 30 秒版、2 分钟版、深挖版演练
- Day 6-7：模拟面试，补齐答不顺的问题

---

## 第九部分：推荐阅读

### 必读论文
1. Attention Is All You Need（Transformer）
2. LLaVA: Visual Instruction Tuning
3. CLIP
4. A Path Towards Autonomous Machine Intelligence（LeCun, 2022）
5. V-JEPA
6. LoRA: Low-Rank Adaptation of Large Language Models
7. Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks

### 推荐博客 / 视频
- Lilian Weng 的 LLM 系列博客（Agent、RAG、Prompt Engineering）
- Andrej Karpathy 的 Let's build GPT
- Yann LeCun 的公开演讲（YouTube）
- vLLM 官方文档与博客

---

*最后更新：2026-06-27 — 强化应用层、系统设计、项目评估与面试表达*
