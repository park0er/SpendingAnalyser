# MiniMax 二级分类自动打标工具使用说明

当你在面板上看到有交易记录显示“待打标”时，说明这些记录已经生成了供大模型阅读的分类提示词（存放在 `output/tagging_batches/` 目录下），但还没有让大模型去执行分类。

我们使用 **MiniMax 开放平台** 提供的大模型 API 来完成自动阅读和打标。

## 准备工作：获取 API Key
1. 访问 [MiniMax 开放平台](https://platform.minimaxi.com/login) 注册并登录账号。
2. 进入“接口密钥”页面，点击 **创建 Coding Plan Key** 或新建普通的 API Key。
3. 复制生成的那一长串 `sk-xxxxx...` 的文本，这就是你的专属 API 密钥，**请不要泄露给他人或上传到公开的 GitHub 仓库**。

## 开始自动打标

如果你是不太懂编程的新手，请完全按照以下步骤在终端（Terminal）中操作：

**第一步：进入项目目录**
在你的终端里，首先确保你已经进入了 `SpendingAnalyser` 所在的目录：
```bash
cd /Users/park0er/Coding/PersonalMatters/Financial/SpendingAnalyser
```
*(注意：请把上面的路径替换为你电脑中实际的项目路径)*

**第二步：设置你的专属密钥 (API Key)**
复制下面这行命令，把引号里面的内容替换成你刚才在网页上复制的真实 API Key，然后按回车执行。（这步操作不会有任何返回提示，是正常的）
```bash
export MINIMAX_API_KEY="sk-xxxxxxxxxxxxxxxxxxxxxxxx"
```

**第三步：启动智能打标程序**
随后，直接运行以下命令：
```bash
python3 src/classifiers/minimax_tagger.py
```

## 运行结果
程序运行后，你会看到类似下面这样的进度条：
```text
🚀 Found 75 batches. Starting MiniMax tagging...
Tagging: 100%|██████████████████████| 75/75 [00:45<00:00,  1.67it/s]

✅ Tagging completed! Generating new CSV...
🎉 CSV successfully updated!
```

当看到 `CSV successfully updated!` 时，打标就全部完成了！所有结果会自动写回底层数据库。

最后，你只需要回到终端重新运行 `bash start.sh`，再刷新你的浏览器仪表盘，就能看到所有账单都拥有了准确的二级分类标签。
