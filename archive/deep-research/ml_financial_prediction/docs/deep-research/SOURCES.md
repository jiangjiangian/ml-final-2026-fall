# 來源與證據索引

本輪有**63筆已查核來源證據、11筆去重學術／工具書目**；來源筆數包含同一論文的metadata、作者稿及出版者稿，不能當成不同論文數。

原始HTML／PDF保存在Git外。以下每筆記錄實際內容hash與閱讀範圍；HTTP200不自動算有效文章，未讀全文不宣稱全文已讀。完整機器可讀索引見[sources.json](sources.json)，失敗／JS外殼等限制見[access_limitations.json](access_limitations.json)，書目與缺欄處理見[citation_audit.json](citation_audit.json)。

Kaggle正式指標名稱以匿名公開GetCompetition RPC查得；POST方法在此只讀metadata，沒有提交預測。第三方reader的Kaggle問題描述與官方RPC分開標記，reader沒有提供可靠的evaluation公式。

本輪文獻工具使用citation-management，依其要求列Kassis等2026 Scientific Agent Skills方法來源（FIN03／Kassis2026）；該引用不支持任何金融增益主張。

以下為代理查核，尚無人類投稿審閱簽核。沒有執行pstack外部腳本或將其自動merge／通知設定當成本會話授權。

### AGT01

**GitHub profile, identity lead**

- 原頁：https://api.github.com/users/poteto
- 實際取得：https://api.github.com/users/poteto
- 查核範圍：Public profile identity only; current employer label is not historical employment proof
- 位置：JSON login/name/company/bio/html_url
- 類型：`author_profile`；取得：`2026-10-30T14:20:17.307075+00:00`。
- 內容SHA256：`402c0ffcb515cee6f0483c29c7d6210ccb8cde16c529bfa90261a7f353f60c04`。

### AGT03

**Meet the Team – React**

- 原頁：https://react.dev/community/team
- 實際取得：https://react.dev/community/team
- 查核範圍：Lauren Tan team entry and linked poteto identity
- 位置：Lauren Tan / Engineer at Cursor entry
- 類型：`official_documentation`；取得：`2026-10-30T14:20:17.311920+00:00`。
- 內容SHA256：`008bedfef5fb8ee72b4efce1c65aed39013737c82ffdc2238409bbab8e02b073`。

### AGT04

**Best practices for coding with agents · Cursor**

- 原頁：https://cursor.com/blog/agent-best-practices
- 實際取得：https://cursor.com/blog/agent-best-practices
- 查核範圍：Planning, context management, rules/skills and verifiable agent loops sections
- 位置：Start with plans; Managing context; Rules; Skills
- 類型：`official_engineering_article`；取得：`2026-10-30T14:20:17.314032+00:00`。
- 內容SHA256：`b6d30a835373a10ad18f04e6cdb3e427a29a2e5ef8b19787dc49680d04ffb484`。

### AGT05

**Harness engineering: leveraging Codex in an agent-first world | OpenAI**

- 原頁：https://openai.com/index/harness-engineering/
- 實際取得：https://openai.com/index/harness-engineering/
- 查核範圍：Author, human steering, environment, repository knowledge and executable invariants sections
- 位置：By Ryan Lopopolo; Redefining role; repository knowledge; enforcing architecture
- 類型：`official_engineering_case`；取得：`2026-10-30T14:20:17.315484+00:00`。
- 內容SHA256：`3b139034f9377ac813f27dc3792abde61b07e06f2ead8382d6353ff2b424fbea`。

### AGT06

**Best practices for Claude Code - Claude Code Docs**

- 原頁：https://code.claude.com/docs/en/best-practices
- 實際取得：https://code.claude.com/docs/en/best-practices
- 查核範圍：Specific prompts, verification, deterministic versus model-decided rules, context sections
- 位置：Tell Claude what it cannot see; Give Claude a check; Enforce rules
- 類型：`official_documentation`；取得：`2026-10-30T14:20:17.318018+00:00`。
- 內容SHA256：`426f637de32d62da3f1eae6ce0cea7ce28f9b8255077b295d947ec0cabd0a86c`。

### AGT12

**Official pstack README**

- 原頁：https://raw.githubusercontent.com/cursor/plugins/main/pstack/README.md
- 實際取得：https://raw.githubusercontent.com/cursor/plugins/main/pstack/README.md
- 查核範圍：README quality/parallelism, principle index, planning preference and compatibility scope
- 位置：README principles / why are there no planning skills
- 類型：`author_official_repository`；取得：`2026-10-30T14:22:15.935610+00:00`。
- 內容SHA256：`7209937a990b0fee0c16702b8f9e8d75737627f99611cc04ac3a27408f6a23d3`。

### AGT13

**Pin official plugins revision**

- 原頁：https://api.github.com/repos/cursor/plugins/commits/main
- 實際取得：https://api.github.com/repos/cursor/plugins/commits/main
- 查核範圍：Commit SHA only, used to pin public pstack research sources
- 位置：$.sha
- 類型：`official_repository_metadata`；取得：`2026-10-30T14:22:15.936375+00:00`。
- 內容SHA256：`a5907b8a24e26cf60d34cc0c4f4fe18e2086301bb796dd4f0dd9c0d6986664ac`。

### AGT14

**Author verification example**

- 原頁：https://raw.githubusercontent.com/poteto/verification-skill-example/main/README.md
- 實際取得：https://raw.githubusercontent.com/poteto/verification-skill-example/main/README.md
- 查核範圍：Complete README; fictional product and omitted driver explicitly noted
- 位置：Private reference; How an agent uses it
- 類型：`author_example_not_product_validation`；取得：`2026-10-30T14:22:15.936933+00:00`。
- 內容SHA256：`81730139c215401e3bbd3e8a251235f3885e8da0121c3f1511f1e6d28456d746`。

### AGT15

**Author persistent memory example**

- 原頁：https://raw.githubusercontent.com/poteto/brainmaxxing/main/README.md
- 實際取得：https://raw.githubusercontent.com/poteto/brainmaxxing/main/README.md
- 查核範圍：README persistent markdown memory and reflect/prune workflow
- 位置：Usage; Installation
- 類型：`author_repository`；取得：`2026-10-30T14:22:15.939502+00:00`。
- 內容SHA256：`bf2f3f0b2c039c9322456aaa37292da03938745512e4f831ef17b1837121fc7c`。

### AGT17

**pstack | Cursor Plugins**

- 原頁：https://cursor.com/marketplace/cursor/pstack
- 實際取得：https://cursor.com/marketplace/cursor/pstack
- 查核範圍：Correct official marketplace entry and publisher label
- 位置：pstack marketplace listing
- 類型：`official_marketplace`；取得：`2026-10-30T14:22:15.947470+00:00`。
- 內容SHA256：`4d7b0629f51798462c125aeb0771eb34f5969e449369573f6a4427e458b8b231`。

### AGT18

**Pinned Lauren Tan pstack source; read only, not adopted as runtime instructions**

- 原頁：https://raw.githubusercontent.com/cursor/plugins/4dd1d05818d19792e7cd6e818f1667f95f7e1dbe/pstack/skills/principle-laziness-protocol/SKILL.md
- 實際取得：https://raw.githubusercontent.com/cursor/plugins/4dd1d05818d19792e7cd6e818f1667f95f7e1dbe/pstack/skills/principle-laziness-protocol/SKILL.md
- 查核範圍：Complete short principle/playbook read; researched as source, not executed as instructions
- 位置：Pinned SKILL/playbook full text
- 類型：`pinned_author_workflow`；取得：`2026-10-30T14:24:28.072670+00:00`。
- 內容SHA256：`1be6e7a435f26a75a76eb848b9c3d611b9977d0f5822361753244da25ca3ca45`。

### AGT19

**Pinned Lauren Tan pstack source; read only, not adopted as runtime instructions**

- 原頁：https://raw.githubusercontent.com/cursor/plugins/4dd1d05818d19792e7cd6e818f1667f95f7e1dbe/pstack/skills/principle-prove-it-works/SKILL.md
- 實際取得：https://raw.githubusercontent.com/cursor/plugins/4dd1d05818d19792e7cd6e818f1667f95f7e1dbe/pstack/skills/principle-prove-it-works/SKILL.md
- 查核範圍：Complete short principle/playbook read; researched as source, not executed as instructions
- 位置：Pinned SKILL/playbook full text
- 類型：`pinned_author_workflow`；取得：`2026-10-30T14:24:28.073430+00:00`。
- 內容SHA256：`ec79a15025bac8d33d62011c54f3b612733fd2a024e623b531b3637aa75070e2`。

### AGT20

**Pinned Lauren Tan pstack source; read only, not adopted as runtime instructions**

- 原頁：https://raw.githubusercontent.com/cursor/plugins/4dd1d05818d19792e7cd6e818f1667f95f7e1dbe/pstack/skills/principle-guard-the-context-window/SKILL.md
- 實際取得：https://raw.githubusercontent.com/cursor/plugins/4dd1d05818d19792e7cd6e818f1667f95f7e1dbe/pstack/skills/principle-guard-the-context-window/SKILL.md
- 查核範圍：Complete short principle/playbook read; researched as source, not executed as instructions
- 位置：Pinned SKILL/playbook full text
- 類型：`pinned_author_workflow`；取得：`2026-10-30T14:24:28.079121+00:00`。
- 內容SHA256：`af0b9dd70b43628ce4a59a4d332e9d9ad055084e460f430e7a757495c627e81a`。

### AGT21

**Pinned Lauren Tan pstack source; read only, not adopted as runtime instructions**

- 原頁：https://raw.githubusercontent.com/cursor/plugins/4dd1d05818d19792e7cd6e818f1667f95f7e1dbe/pstack/skills/poteto-mode/playbooks/hillclimb.md
- 實際取得：https://raw.githubusercontent.com/cursor/plugins/4dd1d05818d19792e7cd6e818f1667f95f7e1dbe/pstack/skills/poteto-mode/playbooks/hillclimb.md
- 查核範圍：Complete short principle/playbook read; researched as source, not executed as instructions
- 位置：Pinned SKILL/playbook full text
- 類型：`pinned_author_workflow`；取得：`2026-10-30T14:24:28.080530+00:00`。
- 內容SHA256：`942c1565b75ad02a2cb6230dd7c1ebd87e19f59a00319ebac2b6616007bf018f`。

### AGT22

**Pinned Lauren Tan pstack source; read only, not adopted as runtime instructions**

- 原頁：https://raw.githubusercontent.com/cursor/plugins/4dd1d05818d19792e7cd6e818f1667f95f7e1dbe/pstack/skills/poteto-mode/playbooks/autonomous-run.md
- 實際取得：https://raw.githubusercontent.com/cursor/plugins/4dd1d05818d19792e7cd6e818f1667f95f7e1dbe/pstack/skills/poteto-mode/playbooks/autonomous-run.md
- 查核範圍：Complete short principle/playbook read; researched as source, not executed as instructions
- 位置：Pinned SKILL/playbook full text
- 類型：`pinned_author_workflow`；取得：`2026-10-30T14:24:28.084372+00:00`。
- 內容SHA256：`e74323411b5a760ffa7393d908d07fed420c68f8dc2aed1267505eaeadf130f2`。

### AGT24

**Provide context with GEMINI.md files | Gemini CLI**

- 原頁：https://geminicli.com/docs/cli/gemini-md/
- 實際取得：https://geminicli.com/docs/cli/gemini-md/
- 查核範圍：Hierarchical project context sections only; no claim this runtime has Google CLI capabilities
- 位置：Understand the context hierarchy
- 類型：`official_documentation`；取得：`2026-10-30T14:35:09.888571+00:00`。
- 內容SHA256：`2b0d60bebef3481fae272aa27f40984cddff8c62ee039844f3074542eb3a01ea`。

### AGT25

**Pinned official README identity check**

- 原頁：https://raw.githubusercontent.com/cursor/plugins/4dd1d05818d19792e7cd6e818f1667f95f7e1dbe/pstack/README.md
- 實際取得：https://raw.githubusercontent.com/cursor/plugins/4dd1d05818d19792e7cd6e818f1667f95f7e1dbe/pstack/README.md
- 查核範圍：README quality/parallelism, principle index, planning preference and compatibility scope
- 位置：README principles / why are there no planning skills
- 類型：`author_official_repository`；取得：`2026-10-30T14:52:32.533438+00:00`。
- 內容SHA256：`7209937a990b0fee0c16702b8f9e8d75737627f99611cc04ac3a27408f6a23d3`。

### CMP01

**Jane Street Blog - Announcing Our Market Prediction Kaggle Competition**

- 原頁：https://blog.janestreet.com/announcing-our-market-prediction-kaggle-competition-index/
- 實際取得：https://blog.janestreet.com/announcing-our-market-prediction-kaggle-competition-index/
- 查核範圍：Complete short organizer announcement; contest purpose, not winning-model proof
- 位置：2020 announcement main body
- 類型：`competition_organizer`；取得：`2026-10-30T14:20:18.896949+00:00`。
- 內容SHA256：`e7f954da97bf40c82325525f94cd245195c237e152c0fc17edc80f3e78e71c1e`。

### CMP09

**SIGKDD - KDD Cup**

- 原頁：https://www.kdd.org/kdd-cup
- 實際取得：https://www.kdd.org/kdd-cup
- 查核範圍：Visible archive and competition definition only; visible list ends at 2016
- 位置：KDD Cup definition and archive table
- 類型：`official_archive_partial`；取得：`2026-10-30T14:20:19.761329+00:00`。
- 內容SHA256：`7b7115cae39efa285cb69262f6ca9b722c92b3dc891c00fdf574a24b0f306d05`。

### CMP10

**Public evaluation page through third party text renderer; not publisher bytes**

- 原頁：https://r.jina.ai/https://www.kaggle.com/competitions/jane-street-real-time-market-data-forecasting/overview/evaluation
- 實際取得：https://r.jina.ai/https://www.kaggle.com/competitions/jane-street-real-time-market-data-forecasting/overview/evaluation
- 查核範圍：Problem description through third-party reader; evaluation formula was not rendered
- 位置：Markdown Content description; not full evaluation
- 類型：`secondary_text_render_of_official_description`；取得：`2026-10-30T14:22:16.360491+00:00`。
- 內容SHA256：`813cf3d19d98399497255b7fb8e5cef597a15e51679cf4ecab188ff27f52c67b`。

### CMP11

**Public Optiver evaluation text renderer**

- 原頁：https://r.jina.ai/https://www.kaggle.com/competitions/optiver-trading-at-the-close/overview/evaluation
- 實際取得：https://r.jina.ai/https://www.kaggle.com/competitions/optiver-trading-at-the-close/overview/evaluation
- 查核範圍：Problem description through third-party reader; evaluation formula was not rendered
- 位置：Markdown Content description; not full evaluation
- 類型：`secondary_text_render_of_official_description`；取得：`2026-10-30T14:22:16.381909+00:00`。
- 內容SHA256：`b1608eb8c2f72d25e9d4c169835b261ada70daff904eeef63ff7f69262ab7c18`。

### CMP12

**Public volatility evaluation text renderer**

- 原頁：https://r.jina.ai/https://www.kaggle.com/competitions/optiver-realized-volatility-prediction/overview/evaluation
- 實際取得：https://r.jina.ai/https://www.kaggle.com/competitions/optiver-realized-volatility-prediction/overview/evaluation
- 查核範圍：Problem description through third-party reader; evaluation formula was not rendered
- 位置：Markdown Content description; not full evaluation
- 類型：`secondary_text_render_of_official_description`；取得：`2026-10-30T14:22:16.392444+00:00`。
- 內容SHA256：`87b4bab1603f6243d5a0c7676cce2ebf65d10511b5fe27ef633c42b238caa747`。

### CMP15

**Participant solution, ranking self-report not organizer-certified**

- 原頁：https://raw.githubusercontent.com/Leo1998-Lu/Optiver-Realized-Volatility-Prediction/main/README.md
- 實際取得：https://raw.githubusercontent.com/Leo1998-Lu/Optiver-Realized-Volatility-Prediction/main/README.md
- 查核範圍：Complete participant README; methods are self-report and ranking not independently certified
- 位置：Solution; feature engineering; validation; ensemble
- 類型：`participant_primary_account`；取得：`2026-10-30T14:35:10.575808+00:00`。
- 內容SHA256：`50ccce466dcc7c137f30bca226e7396e4112144202de840b8e507b5fc0cc825f`。

### CMPAPI1

**Jane Street Market Prediction — public metadata**

- 原頁：https://www.kaggle.com/competitions/jane-street-market-prediction
- 實際取得：https://www.kaggle.com/api/i/competitions.CompetitionService/GetCompetition
- 查核範圍：Official anonymous read-only metadata response, not account access or model submission
- 位置：$.evaluationAlgorithm; $.onlyAllowKernelSubmissions; $.usesSynchronousReruns; $.publicLeaderboardDisclaimerMessage
- 類型：`official_public_competition_rpc`；取得：`2026-10-30T14:25:45.867988+00:00`。
- 內容SHA256：`36eb8d3e55659c2093312f15a9c3665c823217e3d82721966b370426677509ee`。

### CMPAPI2

**Jane Street Real-Time Market Data Forecasting — public metadata**

- 原頁：https://www.kaggle.com/competitions/jane-street-real-time-market-data-forecasting
- 實際取得：https://www.kaggle.com/api/i/competitions.CompetitionService/GetCompetition
- 查核範圍：Official anonymous read-only metadata response, not account access or model submission
- 位置：$.evaluationAlgorithm; $.onlyAllowKernelSubmissions; $.usesSynchronousReruns; $.publicLeaderboardDisclaimerMessage
- 類型：`official_public_competition_rpc`；取得：`2026-10-30T14:25:45.868217+00:00`。
- 內容SHA256：`08c34df5c56a0ab3494e7ddf64c790ab15cfe9e0ea1c115614161e7f87ed86e4`。

### CMPAPI3

**Optiver - Trading at the Close — public metadata**

- 原頁：https://www.kaggle.com/competitions/optiver-trading-at-the-close
- 實際取得：https://www.kaggle.com/api/i/competitions.CompetitionService/GetCompetition
- 查核範圍：Official anonymous read-only metadata response, not account access or model submission
- 位置：$.evaluationAlgorithm; $.onlyAllowKernelSubmissions; $.usesSynchronousReruns; $.publicLeaderboardDisclaimerMessage
- 類型：`official_public_competition_rpc`；取得：`2026-10-30T14:25:45.928617+00:00`。
- 內容SHA256：`5b148a03743f5b73b42533bdaa4ce5cc5618be19cb6b9b06905ee760dc4dbb22`。

### CMPAPI4

**Optiver Realized Volatility Prediction — public metadata**

- 原頁：https://www.kaggle.com/competitions/optiver-realized-volatility-prediction
- 實際取得：https://www.kaggle.com/api/i/competitions.CompetitionService/GetCompetition
- 查核範圍：Official anonymous read-only metadata response, not account access or model submission
- 位置：$.evaluationAlgorithm; $.onlyAllowKernelSubmissions; $.usesSynchronousReruns; $.publicLeaderboardDisclaimerMessage
- 類型：`official_public_competition_rpc`；取得：`2026-10-30T14:25:45.886770+00:00`。
- 內容SHA256：`9d5f54c5fb13b8151ca76de003900aa54c9523015de0078b7a752ad6c2b81ffc`。

### CMPAPI5

**JPX Tokyo Stock Exchange Prediction — public metadata**

- 原頁：https://www.kaggle.com/competitions/jpx-tokyo-stock-exchange-prediction
- 實際取得：https://www.kaggle.com/api/i/competitions.CompetitionService/GetCompetition
- 查核範圍：Official anonymous read-only metadata response, not account access or model submission
- 位置：$.evaluationAlgorithm; $.onlyAllowKernelSubmissions; $.usesSynchronousReruns; $.publicLeaderboardDisclaimerMessage
- 類型：`official_public_competition_rpc`；取得：`2026-10-30T14:25:46.030441+00:00`。
- 內容SHA256：`1d005b5484c376ad20b7e321fd9dcfaa1fc268dd61cb02c80992c33abcfe5b8e`。

### CMPAPI6

**G-Research Crypto Forecasting  — public metadata**

- 原頁：https://www.kaggle.com/competitions/g-research-crypto-forecasting
- 實際取得：https://www.kaggle.com/api/i/competitions.CompetitionService/GetCompetition
- 查核範圍：Official anonymous read-only metadata response, not account access or model submission
- 位置：$.evaluationAlgorithm; $.onlyAllowKernelSubmissions; $.usesSynchronousReruns; $.publicLeaderboardDisclaimerMessage
- 類型：`official_public_competition_rpc`；取得：`2026-10-30T14:25:46.112948+00:00`。
- 內容SHA256：`348e262f6c24a917ba9c7dcfefd298c7bf15b06fc140f6055fa26855d6f3a861`。

### CMPAPI7

**Two Sigma Financial Modeling Challenge — public metadata**

- 原頁：https://www.kaggle.com/competitions/two-sigma-financial-modeling
- 實際取得：https://www.kaggle.com/api/i/competitions.CompetitionService/GetCompetition
- 查核範圍：Official anonymous read-only metadata response, not account access or model submission
- 位置：$.evaluationAlgorithm; $.onlyAllowKernelSubmissions; $.usesSynchronousReruns; $.publicLeaderboardDisclaimerMessage
- 類型：`official_public_competition_rpc`；取得：`2026-10-30T14:25:46.034493+00:00`。
- 內容SHA256：`8d517e36291583e8e0516015e942742a6f13c9ba33741ebe19a87cc53475de04`。

### DAT01

**Events that trigger workflows - GitHub Docs**

- 原頁：https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule
- 實際取得：https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule
- 查核範圍：Schedule and workflow_dispatch restrictions, UTC default, delay/drop warnings
- 位置：schedule section L1923 onward; workflow_dispatch L2220 onward
- 類型：`official_documentation`；取得：`2026-10-30T14:20:17.977140+00:00`。
- 內容SHA256：`68b010ddab0f4e4bf1454c262c62968b1c51e94c939a40c9aa3584650b454849`。

### DAT02

**Get Started with DVC | Data Version Control · DVC**

- 原頁：https://dvc.org/doc/start/data-management/data-versioning
- 實際取得：https://dvc.org/doc/start/data-management/data-versioning
- 查核範圍：Data versioning tutorial concepts; not an installed integration
- 位置：Data versioning / Git pointer / cache
- 類型：`official_documentation`；取得：`2026-10-30T14:20:18.308185+00:00`。
- 內容SHA256：`86b62ea525b76d8be97c7b037e1d02052214983394022c56555a0392fb38124d`。

### DAT03

**get | Data Version Control · DVC**

- 原頁：https://dvc.org/doc/command-reference/get
- 實際取得：https://dvc.org/doc/command-reference/get
- 查核範圍：Get command, revision selection and output paths
- 位置：Description; --rev; --out examples
- 類型：`official_documentation`；取得：`2026-10-30T14:20:18.434887+00:00`。
- 內容SHA256：`18a76bf71718ae20b44158faeff4caa753c0e1fdb5eaad22cda777d15ee63acd`。

### DAT04

**Amazon S3 | Data Version Control · DVC**

- 原頁：https://dvc.org/doc/user-guide/data-management/remote-storage/amazon-s3
- 實際取得：https://dvc.org/doc/user-guide/data-management/remote-storage/amazon-s3
- 查核範圍：DVC S3 remote configuration and authentication options
- 位置：Amazon S3 remote
- 類型：`official_documentation`；取得：`2026-10-30T14:20:18.481713+00:00`。
- 內容SHA256：`a48b298dbbddcbdeb0b678069d5d1736d4b344cdea3348b205a6efdfe9ccde3d`。

### DAT06

**Configuring OpenID Connect in Amazon Web Services - GitHub Docs**

- 原頁：https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws
- 實際取得：https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws
- 查核範圍：OIDC short-lived role and trust scoping
- 位置：Configuring role and trust policy
- 類型：`official_documentation`；取得：`2026-10-30T14:20:18.869062+00:00`。
- 內容SHA256：`159491200e6a7a9424375db68256c042fc07ed02249bdd951fcdf106c9ba64e9`。

### DAT07

**Retaining multiple versions of objects with S3 Versioning - Amazon Simple Storage Service**

- 原頁：https://docs.aws.amazon.com/AmazonS3/latest/userguide/Versioning.html
- 實際取得：https://docs.aws.amazon.com/AmazonS3/latest/userguide/Versioning.html
- 查核範圍：Versioning semantics, default state and full-object charging
- 位置：Retaining multiple versions; unversioned default; rates
- 類型：`official_documentation`；取得：`2026-10-30T14:35:09.166838+00:00`。
- 內容SHA256：`f93127f6232c52defa47253f1222034c35de361b3fcabc91ff5b89ff752f6292`。

### DAT08

**How to prevent object overwrites with conditional writes - Amazon Simple Storage Service**

- 原頁：https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-writes.html
- 實際取得：https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-writes.html
- 查核範圍：Conditional writes and actual If-None-Match / If-Match capability
- 位置：Conditional write behavior / put-object options
- 類型：`official_documentation`；取得：`2026-10-30T14:35:09.285889+00:00`。
- 內容SHA256：`5cd578af7f00b4dd10376105bbf66e77c15c8a6a752f87a66ab218610414fc62`。

### DAT09

**put-object — AWS CLI 2.39.2 Command Reference**

- 原頁：https://docs.aws.amazon.com/cli/latest/reference/s3api/put-object.html
- 實際取得：https://docs.aws.amazon.com/cli/latest/reference/s3api/put-object.html
- 查核範圍：Conditional writes and actual If-None-Match / If-Match capability
- 位置：Conditional write behavior / put-object options
- 類型：`official_documentation`；取得：`2026-10-30T14:35:09.823667+00:00`。
- 內容SHA256：`5d4d8679fa6a6b84cc9996dc2cadc984796198977f477c9044c726b9f9e1e207`。

### DAT10

**Downloading workflow artifacts - GitHub Docs**

- 原頁：https://docs.github.com/en/actions/how-tos/manage-workflow-runs/download-workflow-artifacts
- 實際取得：https://docs.github.com/en/actions/how-tos/manage-workflow-runs/download-workflow-artifacts
- 查核範圍：Complete artifact download page, read-access requirement and retention
- 位置：Who can use; retention; gh run download
- 類型：`official_documentation`；取得：`2026-10-30T14:49:17.198383+00:00`。
- 內容SHA256：`5bd88bf20a6dc616112c338e7cca3046a268cc128a92f73e636f835145745b77`。

### FIN03

**[2609.00065] Scientific Agent Skills: A Library of Procedural Knowledge for Research Agents**

- 原頁：https://arxiv.org/abs/2609.00065
- 實際取得：https://arxiv.org/abs/2609.00065
- 查核範圍：Current arXiv citation tags / authors / year; method citation only
- 位置：citation_title / citation_author / citation_date / citation_arxiv_id
- 類型：`preprint_metadata`；取得：`2026-10-30T14:20:20.623393+00:00`。
- 內容SHA256：`67cc1bf1d1a285943f563765900dcd3bd12c7ecf884903c05468e261b94068ce`。

### FIN07

**Empirical Asset Pricing via Machine Learning**

- 原頁：https://api.crossref.org/works/10.1093/rfs/hhaa009
- 實際取得：https://api.crossref.org/works/10.1093/rfs/hhaa009
- 查核範圍：Published metadata; abstracts only when the record actually supplies one
- 位置：$.message.title/author/published-print/published-online/container-title/volume/issue/page/DOI/abstract
- 類型：`crossref_publisher_deposited_metadata`；取得：`2026-10-30T14:22:16.555121+00:00`。
- 內容SHA256：`5a709484455029391eb6371fa6f370cd8a4a24f633e0e91aa0926ee21b5e71bb`。

### FIN09

**… and the Cross-Section of Expected Returns**

- 原頁：https://api.crossref.org/works/10.1093/rfs/hhv059
- 實際取得：https://api.crossref.org/works/10.1093/rfs/hhv059
- 查核範圍：Published metadata; abstracts only when the record actually supplies one
- 位置：$.message.title/author/published-print/published-online/container-title/volume/issue/page/DOI/abstract
- 類型：`crossref_publisher_deposited_metadata`；取得：`2026-10-30T14:22:17.411833+00:00`。
- 內容SHA256：`12b2120c42d31791a2a94468b6e9844685371a4d1066f05872192aa8cf3629bd`。

### FIN12

**MASTER: Market-Guided Stock Transformer for Stock Price Forecasting 							| Proceedings of the AAAI Conference on Artificial Intelligence**

- 原頁：https://ojs.aaai.org/index.php/AAAI/article/view/27767
- 實際取得：https://ojs.aaai.org/index.php/AAAI/article/view/27767
- 查核範圍：Official AAAI authors, abstract, publication date and citation metadata
- 位置：Authors; Abstract; How to Cite; citation meta tags
- 類型：`official_proceedings`；取得：`2026-10-30T14:22:17.807803+00:00`。
- 內容SHA256：`77c20d118b904a6700157e9c1ed00d268f528b6d6a143d518bd93f258224a037`。

### FIN13

**[1904.04912] Enhancing Time Series Momentum Strategies Using Deep Neural Networks**

- 原頁：https://arxiv.org/abs/1904.04912
- 實際取得：https://arxiv.org/abs/1904.04912
- 查核範圍：Abstract and publication metadata only; no full-paper performance audit
- 位置：arXiv abstract and Journal reference
- 類型：`author_preprint_abstract`；取得：`2026-10-30T14:22:17.925116+00:00`。
- 內容SHA256：`d04793806f5358a0560898b9cfa99100c40259b2add52eee1636e0ad0f7d39c3`。

### FIN15

**Deep forecasting survey original paper**

- 原頁：https://arxiv.org/pdf/2004.13408
- 實際取得：https://arxiv.org/pdf/2004.13408
- 查核範圍：Physical PDF pages 1-4: introduction and CNN/RNN methodology; not entire survey
- 位置：PDF physical pages 1-4; selected-page evidence file
- 類型：`author_open_manuscript_selected_sections`；取得：`2026-10-30T14:24:28.517894+00:00`。
- 內容SHA256：`efb3cc1dfbeb269a11201aae1caca1413fc6aa65bd0363a8490398986dfad248`。

### FIN16

**Author working paper version of published financial ML study**

- 原頁：https://www.nber.org/system/files/working_papers/w25398/w25398.pdf
- 實際取得：https://www.nber.org/system/files/working_papers/w25398/w25398.pdf
- 查核範圍：Physical PDF pages 2-4 and 9 plus monthly-prediction passages; 2019 working version, not publisher full text
- 位置：PDF physical pages 2-4,9; text monthly return discussion
- 類型：`author_working_paper_selected_sections`；取得：`2026-10-30T14:24:28.525888+00:00`。
- 內容SHA256：`cf4ebd0a103c7714235c8e464e060c96f9f7332c4e82b2219f2560767d928c66`。

### FIN17

**The probability of backtest overfitting**

- 原頁：https://api.crossref.org/works/10.21314/jcf.2016.322
- 實際取得：https://api.crossref.org/works/10.21314/jcf.2016.322
- 查核範圍：Published metadata; abstracts only when the record actually supplies one
- 位置：$.message.title/author/published-print/published-online/container-title/volume/issue/page/DOI/abstract
- 類型：`crossref_publisher_deposited_metadata`；取得：`2026-10-30T14:35:06.478702+00:00`。
- 內容SHA256：`2f90688a0e1e13a70a46a8e7f24ae8071ab8d9947023c3ce3f1588c5d28014c9`。

### FIN18

**Author full backtest overfitting manuscript**

- 原頁：https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf
- 實際取得：https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf
- 查核範圍：Physical PDF pages 1-3, abstract and introductory multiple-search argument; not all proofs
- 位置：Author February 2015 manuscript, physical pages 1-3
- 類型：`author_open_manuscript_selected_sections`；取得：`2026-10-30T14:35:06.480741+00:00`。
- 內容SHA256：`d8bfbadaaedb430d9dec929646d92f3580fdf18238f34121ae7738fa1c69a63d`。

### FIN20

**Financial Machine Learning**

- 原頁：https://api.crossref.org/works/10.1561/0500000064
- 實際取得：https://api.crossref.org/works/10.1561/0500000064
- 查核範圍：Published metadata; abstracts only when the record actually supplies one
- 位置：$.message.title/author/published-print/published-online/container-title/volume/issue/page/DOI/abstract
- 類型：`crossref_publisher_deposited_metadata`；取得：`2026-10-30T14:35:07.221851+00:00`。
- 內容SHA256：`6b95c42785e68e4ad2632548cda7dafcd7db4482427d897d05475eace1d8d465`。

### FIN21

**Time-series forecasting with deep learning: a survey**

- 原頁：https://api.crossref.org/works/10.1098/rsta.2020.0209
- 實際取得：https://api.crossref.org/works/10.1098/rsta.2020.0209
- 查核範圍：Published metadata; abstracts only when the record actually supplies one
- 位置：$.message.title/author/published-print/published-online/container-title/volume/issue/page/DOI/abstract
- 類型：`crossref_publisher_deposited_metadata`；取得：`2026-10-30T14:35:07.468418+00:00`。
- 內容SHA256：`7ac92728a6f2b2f60f1fa769c5846e792767dbc07a0a80b21e5c1fbaf25344ad`。

### FIN22

**Enhancing Time-Series Momentum Strategies Using Deep Neural Networks**

- 原頁：https://api.crossref.org/works/10.3905/jfds.2019.1.015
- 實際取得：https://api.crossref.org/works/10.3905/jfds.2019.1.015
- 查核範圍：Published metadata; abstracts only when the record actually supplies one
- 位置：$.message.title/author/published-print/published-online/container-title/volume/issue/page/DOI/abstract
- 類型：`crossref_publisher_deposited_metadata`；取得：`2026-10-30T14:35:07.652548+00:00`。
- 內容SHA256：`4ec06a5e41f86ecde03a7b3b4f5fe8fa51899cc90c3b271abb4adcbeb974f175`。

### FIN23

**Does Academic Research Destroy Stock Return Predictability?**

- 原頁：https://api.crossref.org/works/10.1111/jofi.12365
- 實際取得：https://api.crossref.org/works/10.1111/jofi.12365
- 查核範圍：Published metadata; abstracts only when the record actually supplies one
- 位置：$.message.title/author/published-print/published-online/container-title/volume/issue/page/DOI/abstract
- 類型：`crossref_publisher_deposited_metadata`；取得：`2026-10-30T14:35:08.059941+00:00`。
- 內容SHA256：`f703c0e9a80cb1cc0efb9829f273ea8e76b8d950bab05363aa5a5a70a8ce9d8d`。

### FIN25

**Holidays & Trading Hours**

- 原頁：https://www.nyse.com/markets/hours-calendars
- 實際取得：https://www.nyse.com/markets/hours-calendars
- 查核範圍：Official NYSE core hours and holiday-calendar scope
- 位置：Core Trading Session 9:30 a.m. to 4:00 p.m. ET
- 類型：`official_exchange_documentation`；取得：`2026-10-30T14:35:08.629318+00:00`。
- 內容SHA256：`9ede5dd8af5a2ffef372d90e1fcac65ce3e9cb74ebab6d67edbce2d4bceae93c`。

### FIN26

**. . . and the Cross-Section of Expected Returns | NBER**

- 原頁：https://www.nber.org/papers/w20592
- 實際取得：https://www.nber.org/papers/w20592
- 查核範圍：NBER abstract and link to published version; no full journal-text reading claim
- 位置：Abstract; citation data
- 類型：`author_working_paper_abstract`；取得：`2026-10-30T14:49:17.198930+00:00`。
- 內容SHA256：`f3e698ddeb6b625cb54b334d0ea539f34a1e22139212c2666efbb02ebbbba3be`。

### FIN27

**Machine Learning :: Jane Street**

- 原頁：https://www.janestreet.com/machine-learning/
- 實際取得：https://www.janestreet.com/machine-learning/
- 查核範圍：Complete visible corporate ML page; company self-description, not independent performance evidence
- 位置：Financial markets noise/regimes; researchers/engineers/traders; neural models
- 類型：`corporate_self_description`；取得：`2026-10-30T14:52:32.533893+00:00`。
- 內容SHA256：`a952451040e8f7463ba33b86782dd6a3cc5008fb6364613a7aaf5f4aed881a7a`。

### FIN28

**Empirical Asset Pricing via Machine Learning**

- 原頁：https://www.aqr.com/Insights/Research/Journal-Article/Empirical-Asset-Pricing-via-Machine-Learning
- 實際取得：https://www.aqr.com/Insights/Research/Journal-Article/Empirical-Asset-Pricing-via-Machine-Learning
- 查核範圍：AQR research summary and published-in link; no inference about private deployed products
- 位置：Empirical Asset Pricing via ML; Published In RFS
- 類型：`corporate_research_summary`；取得：`2026-10-30T14:52:32.536425+00:00`。
- 內容SHA256：`eb623d606fe55a61eccae639ab94f4a2e280ca9deb3254bee1baf2386ed1df5f`。

### MOD01

**[1603.02754] XGBoost: A Scalable Tree Boosting System**

- 原頁：https://arxiv.org/abs/1603.02754
- 實際取得：https://arxiv.org/abs/1603.02754
- 查核範圍：arXiv title/abstract/author metadata, paired with published or full-manuscript source where available
- 位置：arXiv abstract / citation tags
- 類型：`author_preprint_abstract`；取得：`2026-10-30T14:20:19.767468+00:00`。
- 內容SHA256：`5c47cf0189cdd6e0f1418a2acaff61645bf7f0146efd354d174c8cee2c124df6`。

### MOD02

**Features — LightGBM 4.7.0 documentation**

- 原頁：https://lightgbm.readthedocs.io/en/stable/Features.html
- 實際取得：https://lightgbm.readthedocs.io/en/stable/Features.html
- 查核範圍：LightGBM documented boosting features; not installed or benchmarked here
- 位置：Features overview / tree learning
- 類型：`official_software_documentation`；取得：`2026-10-30T14:20:19.907747+00:00`。
- 內容SHA256：`9470cac40b52838302ebade8db572f9ab8347ef484d3d7956bc1f30afab1ad0a`。

### MOD03

**[1803.01271] An Empirical Evaluation of Generic Convolutional and Recurrent Networks for Sequence Modeling**

- 原頁：https://arxiv.org/abs/1803.01271
- 實際取得：https://arxiv.org/abs/1803.01271
- 查核範圍：arXiv title/abstract/author metadata, paired with published or full-manuscript source where available
- 位置：arXiv abstract / citation tags
- 類型：`author_preprint_abstract`；取得：`2026-10-30T14:20:19.978606+00:00`。
- 內容SHA256：`f44657da66da96dae581e206842e16ed1b5b9fcbe089f0c88afd474f40c23a50`。

### MOD05

**GitHub - SJTU-DMTai/MASTER: This is the official code and supplementary materials for our AAAI-2024 paper: MASTER: Market-Guided Stock Transformer for Stock Price Forecasting. MASTER is a stock transformer for stock price forecasting, which models the momentary and cross-time stock correlation and guide feature selection with market information. · GitHub**

- 原頁：https://github.com/SJTU-DMTai/MASTER
- 實際取得：https://github.com/SJTU-DMTai/MASTER
- 查核範圍：README authorship and 2025-06-26 validation/data-processing notices, not a complete code audit
- 位置：Important Notice; About Validation; Dataset
- 類型：`author_repository_with_material_limitations`；取得：`2026-10-30T14:20:20.226962+00:00`。
- 內容SHA256：`a8b3699bd5905d4cb9af295af016184fe3a2b7c0003ea4b67331d9c67eb20325`。

### MOD07

**MASTER full paper official publisher PDF**

- 原頁：https://ojs.aaai.org/index.php/AAAI/article/download/27767/27575
- 實際取得：https://ojs.aaai.org/index.php/AAAI/article/download/27767/27575
- 查核範圍：Physical PDF pages 1-5: target normalization, market gating, intra/inter-stock layers, evaluation
- 位置：AAAI paper physical pages 1-5 / printed pp162-166
- 類型：`publisher_fulltext_selected_sections`；取得：`2026-10-30T14:24:28.509276+00:00`。
- 內容SHA256：`5215526785c8df9fd237a669e7e90c6565831d456d07efdd71aac121b1f1220e`。

### MOD08

**TCN original full paper**

- 原頁：https://arxiv.org/pdf/1803.01271
- 實際取得：https://arxiv.org/pdf/1803.01271
- 查核範圍：Physical PDF pages 1-4: generic sequence tasks and causal/dilated/residual TCN design
- 位置：PDF physical pages 1-4
- 類型：`author_open_manuscript_selected_sections`；取得：`2026-10-30T14:24:28.515120+00:00`。
- 內容SHA256：`f7e5df08b234f1c395ff4f7b3597b28f170fc9d70af388be5b645bfc4456f42b`。

### MOD09

**XGBoost: A Scalable Tree Boosting System**

- 原頁：https://api.crossref.org/works/10.1145/2939672.2939785
- 實際取得：https://api.crossref.org/works/10.1145/2939672.2939785
- 查核範圍：Published metadata; abstracts only when the record actually supplies one
- 位置：$.message.title/author/published-print/published-online/container-title/volume/issue/page/DOI/abstract
- 類型：`crossref_publisher_deposited_metadata`；取得：`2026-10-30T14:49:17.202420+00:00`。
- 內容SHA256：`c00fe17b25c7c88f47183812b5870c692b6d9658e6992f93a1b04aa8aae45a70`。
