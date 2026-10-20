# AI-T12 N1 bounded public-source review

Completed 2026-10-18 02:33 +08. This is a readonly enrichment proposal, not an applied batch or independent registration verification.

Fixed selection: `selection-next-after-w12.json` (`no_usable_retained_lead`, 592 entries), slice `[0:20]`, all 20 accepted after cohort exclusions. The original 1,283-company discovery pass had already attempted these names; new first-discovery coverage is **0**. Each company received exactly one changed query specifying contact fields, location or public directories: 20 queries in five search calls. Search archives are retained separately from actual page evidence; snippets were never imported as body evidence.

Four actual HTTPS GETs produced four saved raw documents and four readable bodies, at most one GET per target. Normal TLS, public-IP checks, no proxy inheritance, redirects disabled, no retry or captcha bypass. The Qingdao government response declared an invalid `utf-8,gbk` HTTP charset; its raw bytes were already saved. UTF-8 BOM and HTML meta permitted offline parsing of that same raw file, with no second request. Initial parse failure and recovery remain in the journal.

Three candidate fields across three companies, all `publication_kind=directory`:

- 中软国际科技服务有限公司: generic email `xzb@chinasoftinc.com`; [exact directory profile](https://highbay.cn/merchant/zhongruanguojikejifuwuyouxiangongsi/). The adjacent group worldwide addresses and group HR/PR/IR contacts were excluded. `chinasofti.com` is not assigned as this subsidiary's independent website.
- 西安未来国际信息股份有限公司: generic email `marketing@ourfuture.cn`; [exact directory profile](https://highbay.cn/merchant/xianweilaiguojixinxigufenyouxiangongsi/). The named-person email was excluded. Existing `research-b.json` records an earlier `ourfuture.cn` failure; that host was not revisited.
- 西安美好家实业有限公司: address `西安曲江新区曲江创意谷文化产业园雁翔路3369号S8幢4层`; [public directory](https://top.qcc.com/tc/c1d4da0e687a.html). Only the exact target's company block was used; unrelated companies, platform footer address and customer-service emails were excluded. City was not inferred from the abbreviated locality string.

The fourth actual body is the [Qingdao government bidding notice](https://ggzy.qingdao.gov.cn/c/TradeDetals-ZtbShow/163244-5070-0-2-0/8935e48d-cf8b-4e39-ad94-c7f28711b23d-B03CE5B6FC1D2D3C2D5FCEBC39AA2406.html). 盈盛科技（西安）有限公司 appears as a bidder, but its own business contacts are absent; inquiry/complaint contact details belong to the purchaser or authority and were not assigned. Personnel and certificate text remains a lead only.

Other results included names-only science lists, old litigation addresses, 2022 project sites, related-parent or near-name pages, masked contacts and HR/platform contacts. Each target's rejection/gap is preserved in the journal. These did not establish absence of a website or phone.

Actual checks: all 20 selected rows reread with SQLite `mode=ro` and `PRAGMA query_only=ON`, exact ID/name/version/fields unchanged. All three target fields remained empty. Source raw SHA, UTF-8 body SHA, original journal SHA and exact contiguous excerpt offsets checked. Existing `validate_batch` executed successfully with SQL, socket and DNS operations explicitly denied. 0 model calls, 0 business writes, 0 frontend/service changes.

Publication dates on the three directories are unknown. The candidate fields are public disclosures pending root review; no current-contact accuracy, ownership, registration status, certificate validity or independent verification is asserted.

Private frozen artifacts: `.runtime/baichuan-ai-local/independent-enrichment-20261017/cohort-leads-n1.json`, `research-leads-n1.json`, `batch-leads-n1.json`, `leads-n1-final-receipt.json`, `leads-n1-search-1.json` through `-5.json`, and `leads-n1-raw/`. Initial and first-10 review checkpoints retained. Only root may apply the reviewed batch.

Batch SHA256: `6a1745623471ed9ccd98c815ade443056ea2a4e3bb1e17b8c69630524a36e036`

Journal SHA256: `06ff6b99f285de659006a4216a1a6d9003e35e6495233bc82500451fa43b832d`
