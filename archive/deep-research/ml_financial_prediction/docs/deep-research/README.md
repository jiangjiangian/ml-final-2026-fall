# 金融競賽與agent工作流深度研究

分支：**deep-research**；基底`dev@675d662`。研究日期2026-10-30。Git不接受含空白的branch名稱，因此以連字號表達使用者要求的「deep research」。本輪成果為研究、設計與設定，沒有啟用排程、建立雲端儲存或執行新模型實驗。

| 你問的問題 | 結論 | 完整交付 |
|---|---|---|
| 每天抓取並讓其他branch共用？ | 目前尚未自動運行。採集者集中抓，原始資料進私有共享儲存，repo保存版本索引；各branch固定同一版本 | [DATA_AUTOMATION](DATA_AUTOMATION.md) |
| 真實競賽／學界／企業怎麼做？ | 先對齊metric／可用時間／驗證方式，再測特徵與模型；七場Kaggle已核實metric名稱，KDD Cup不全是金融 | [COMPETITIONS](COMPETITIONS.md)、[FINANCIAL_METHODS](FINANCIAL_METHODS.md) |
| 至少四種模型如何設計？ | M1正則化線性、M2提升樹、M3因果TCN、M4市場引導跨股attention；統一raw intraday目標與時間驗證 | [MODEL_ARCHITECTURES](MODEL_ARCHITECTURES.md)、[設定](../../configs/research/model_families.json) |
| Lauren Tan如何駕馭agent？ | 找到Cursor官方pstack及作者驗證範例；先建立可跑驗收，再放手與平行；用短契約與證據減少盯梢 | [AGENT_WORKFLOW](AGENT_WORKFLOW.md) |

重要研究發現：MASTER原文的五日／每日去均值ranking target不適用本課絕對盤中方向，不能直接搬loss與top-k策略；作者repo也公開記錄validation/test資料處理與股票全集問題，必須獨立驗收。現有E00–E03負結果與已看過的2026保留期繼續保留；本輪設計不冒稱已提高分數。

來源包含官方競賽公開RPC、ACM／AAAI論文、RFS／Journal of Finance／金融ML綜述、作者開放稿、主辦方與OpenAI／Anthropic／Google／Cursor官方材料。已核對內容與存取限制在[SOURCES](SOURCES.md)，書目在[references.bib](references.bib)，方法與範圍在[RESEARCH_PROTOCOL](RESEARCH_PROTOCOL.md)。有些候選URL被擋、回404或只有JS外殼；它們不作支撐性證據。

文獻工作採用citation-management技能，並依其要求列Scientific Agent Skills方法來源；該引用不是金融效能證據。原始HTML／PDF與處理紀錄保存在Git外`/workspace/shared/research/deep-research-20261030/`。論文只閱讀摘要／指定章節者會明示，沒有假稱全部全文或付費內容已讀。

下一個可執行階段：選定共享儲存與排程入口，實作第二個checkout的同版本下載／核對；之後依R1特徵8設定與R2模型12設定的明確上限實作／比較四種架構。採集可先獨立運作，不必等模型勝出，但正式訓練／提交的時間證據門檻保持。
