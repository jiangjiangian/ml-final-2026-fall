# archive

2026-11-05 封存。這裡放的是 `ml-final-2026-fall` 其他分支在封存當下的完整內容。每個子資料夾的 git tree hash 都和原分支的 tree 相同，所以檔案內容和權限逐位元一樣。

repo 只留 `claude/hopeful-brahmagupta-wikys1`、`claude/peaceful-babbage-09xeie` 和空的 `main` 之後，要找舊東西就來這裡。

| 資料夾 | 原分支 | 封存時的 commit | 最後更新 | 檔案數 | 大小 |
|---|---|---|---|---|---|
| `system-completion/` | system-completion：原本的預設分支，有完整程式、workflows、文件 | `2a4c6cb` | 2026-11-04 | 265 | 11 MB |
| `live-data/` | live-data：老師 Training／Live ZIP、外部資料快照、自動化狀態 | `e5025e6` | 2026-11-05 | 441 | 153 MB |
| `dev/` | dev | `675d662` | 2026-10-30 | 171 | 6.4 MB |
| `deep-research/` | deep-research | `80ac804` | 2026-10-30 | 185 | 7.4 MB |
| 沒有資料夾 | main：本來就是空的 | `84d42ea` | 2026-10-25 | 0 | 0 |
| `old-research/` | 本分支 2026-11-04 的 Phase 2 研究報告（舊的 `deploy/README.md`） | `f1eadef` | 2026-11-04 | 1 | 48 KB |

完整的 commit SHA：

```text
system-completion  2a4c6cbcca7eafa6f79a161ef7155fd537f90a5c
live-data          e5025e62d69dca5ce7070f4fd3da6aadcb766bf9
dev                675d6622490ec0314c22856e9db21556be116c83
deep-research      80ac80439f37d0843e595c675404f4dbe81d8c76
main               84d42ea4ef615f12a864b47ada0b0781e4ccf44f
```

## 這裡的東西不會執行

GitHub 只讀 repo 根目錄的 `.github/workflows/`。`archive/system-completion/.github/workflows/` 裡的排程放在這裡不會跑。

## 刪掉原分支後，歷史還在嗎

`system-completion`、`dev`、`deep-research`、`main` 的每個 commit，都還在兩個 claude 分支的歷史裡，因為兩個 claude 分支都是從 `2a4c6cb` 長出來的。刪掉這四個分支不會丟歷史。要把其中一個分支放回 GitHub，推回它的 SHA 就好：

```bash
git push origin 2a4c6cbcca7eafa6f79a161ef7155fd537f90a5c:refs/heads/system-completion
```

`live-data` 和其他分支沒有共同歷史，它的 12 個 commit 只存在它自己身上。刪掉後，這裡只剩最新的快照。想留下歷史，就在刪除前打一個 tag：

```bash
git push origin e5025e62d69dca5ce7070f4fd3da6aadcb766bf9:refs/tags/archive/live-data
```

封存時，每天的自動化還在寫 `live-data`。封存之後才產生的 commit 不在這裡。

## 用這裡的老師資料重建本分支的 data/

`live-data` 刪掉後，`crawler.py` 讀不到預設的 `origin/live-data`。改成從這裡讀：

```bash
python crawler.py --live-data-ref "$(git rev-parse HEAD:archive/live-data)"
```

這樣會讀到這份快照裡最新的 Training 和 Live ZIP（Training `7433b271…`，Live `eea89fce…`，11/05 取得）。Live ZIP 比 `data/teacher_live/` 現在那份（`7f4c759a…`）新，但本分支只用 9/1～9/30 的列，而這段的列在各版本之間沒有變過。
