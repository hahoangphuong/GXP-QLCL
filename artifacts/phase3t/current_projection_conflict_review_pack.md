# Current Projection Conflict Review Pack

- Generated on: `2026-08-26`
- Source Phase 3p path: `artifacts/phase3p/current_projection_conflicts.json`
- Source Phase 3p sha256: `4d703203e873319613e9b67c6bb8044902848ce64a085d67432d6dc06e40ecf0`
- Source decision contract path: `artifacts/phase3s/current_projection_conflict_decisions.template.json`
- Source decision contract sha256: `f47b24680410f706be7bd511fa949f4364d75fa5e48c129f279db7262818b7d4`
- Source duplicate analysis path: `artifacts/legacy_audit/duplicate_current_analysis.json`
- Source duplicate analysis sha256: `3c8393cbec37ba329ca3e81c6dac61046dcf5a7a6facee4197a337dbfc0e165f`
- Conflict count: `14`

## db.ktra::GMP-103C

- Projection: `current_case_projection`
- Source sheet: `db.ktra`
- Business key: `GMP-103C`
- Classification: `completed_plus_pending_both_current`
- Candidate legacy ids: `1095, 1194`
- Current decision action: `winner`
- Review focus: Xac nhan dong current-case nao moi dung khi mot dong completed va mot dong pending cung dang current.
- Decision question: Legacy inspection row nao phai dai dien cho current case projection cua inspection key nay?
- Resolution rationale: One completed row and one pending row are both marked current; workbook evidence does not yet prove which row should drive the target current-case projection.
- Evidence summary: Progress values=[Chờ đi kiểm tra ..., Hoàn thành]; linked_certificate_ids=[1183]; candidate_row_states=[1095:Chờ đi kiểm tra ..., 1194:Hoàn thành]

### Candidate Details

- legacy_row_id=1095; progress=Chờ đi kiểm tra ...; linked_certificate_id=
- legacy_row_id=1194; progress=Hoàn thành; linked_certificate_id=1183

## db.ktra::GMP-310A

- Projection: `current_case_projection`
- Source sheet: `db.ktra`
- Business key: `GMP-310A`
- Classification: `multiple_completed_both_current`
- Candidate legacy ids: `1047, 1160`
- Current decision action: `winner`
- Review focus: Xac nhan dong current-case winner khi co nhieu dong completed cung dang current.
- Decision question: Legacy inspection row nao phai dai dien cho current case projection cua inspection key nay?
- Resolution rationale: More than one completed inspection row remains current; no proven winner-selection rule exists yet.
- Evidence summary: Progress values=[Hoàn thành, Hoàn thành]; linked_certificate_ids=[1022, 1209]; candidate_row_states=[1047:Hoàn thành, 1160:Hoàn thành]

### Candidate Details

- legacy_row_id=1047; progress=Hoàn thành; linked_certificate_id=1022
- legacy_row_id=1160; progress=Hoàn thành; linked_certificate_id=1209

## db.ktra::GMP-52A

- Projection: `current_case_projection`
- Source sheet: `db.ktra`
- Business key: `GMP-52A`
- Classification: `completed_plus_pending_both_current`
- Candidate legacy ids: `1152, 1509`
- Current decision action: `winner`
- Review focus: Xac nhan dong current-case nao moi dung khi mot dong completed va mot dong pending cung dang current.
- Decision question: Legacy inspection row nao phai dai dien cho current case projection cua inspection key nay?
- Resolution rationale: One completed row and one pending row are both marked current; workbook evidence does not yet prove which row should drive the target current-case projection.
- Evidence summary: Progress values=[Hoàn thành, Chờ hoàn thiện báo cáo ...]; linked_certificate_ids=[1194]; candidate_row_states=[1152:Hoàn thành, 1509:Chờ hoàn thiện báo cáo ...]

### Candidate Details

- legacy_row_id=1152; progress=Hoàn thành; linked_certificate_id=1194
- legacy_row_id=1509; progress=Chờ hoàn thiện báo cáo ...; linked_certificate_id=

## db.ktra::GMP-75B

- Projection: `current_case_projection`
- Source sheet: `db.ktra`
- Business key: `GMP-75B`
- Classification: `completed_plus_pending_both_current`
- Candidate legacy ids: `1126, 1460`
- Current decision action: `winner`
- Review focus: Xac nhan dong current-case nao moi dung khi mot dong completed va mot dong pending cung dang current.
- Decision question: Legacy inspection row nao phai dai dien cho current case projection cua inspection key nay?
- Resolution rationale: One completed row and one pending row are both marked current; workbook evidence does not yet prove which row should drive the target current-case projection.
- Evidence summary: Progress values=[Hoàn thành, Chờ đi kiểm tra ...]; linked_certificate_ids=[1096]; candidate_row_states=[1126:Hoàn thành, 1460:Chờ đi kiểm tra ...]

### Candidate Details

- legacy_row_id=1126; progress=Hoàn thành; linked_certificate_id=1096
- legacy_row_id=1460; progress=Chờ đi kiểm tra ...; linked_certificate_id=

## db.cc::GMP-104

- Projection: `current_certificate_projection`
- Source sheet: `db.cc`
- Business key: `GMP-104`
- Classification: `blank_ma_dc_non_case_backed_multi_current`
- Candidate legacy ids: `845, 1242, 1438, 1475`
- Current decision action: `no_winner`
- Review focus: Chon mot current certificate winner hoac xac nhan khong co winner khi cac dong khong co inspection/case backing.
- Decision question: Legacy certificate row nao phai dai dien cho current certificate projection cua site nay?
- Resolution rationale: Multiple non-case-backed certificate rows collapse onto one current key when MÃ DC is blank; no proven business discriminator exists yet.
- Evidence summary: All candidate rows have blank ma_dc=True and blank inspection_id=True; certificate_nos=[5130408005493, INS-484517-103383276-20874384, OGYÉI/10084-6/2023, OGYÉI/22758-6/2019]

### Candidate Details

- legacy_row_id=845; certificate_no=OGYÉI/22758-6/2019; issue_date=2019-11-28 00:00:00+00:00; expiry_date=30-08-2022 (gia hạn đến 31-12-2023)
- legacy_row_id=1242; certificate_no=OGYÉI/10084-6/2023; issue_date=2023-07-12 00:00:00+00:00; expiry_date=2026-02-09 00:00:00+00:00
- legacy_row_id=1438; certificate_no=5130408005493; issue_date=2022-09-01 00:00:00+00:00; expiry_date=2027-09-01 00:00:00+00:00
- legacy_row_id=1475; certificate_no=INS-484517-103383276-20874384; issue_date=2025-10-07 00:00:00+00:00; expiry_date=2027-05-31 00:00:00+00:00

## db.cc::GMP-128

- Projection: `current_certificate_projection`
- Source sheet: `db.cc`
- Business key: `GMP-128`
- Classification: `blank_ma_dc_non_case_backed_multi_current`
- Candidate legacy ids: `1217, 1244, 1348`
- Current decision action: `no_winner`
- Review focus: Chon mot current certificate winner hoac xac nhan khong co winner khi cac dong khong co inspection/case backing.
- Decision question: Legacy certificate row nao phai dai dien cho current certificate projection cua site nay?
- Resolution rationale: Multiple non-case-backed certificate rows collapse onto one current key when MÃ DC is blank; no proven business discriminator exists yet.
- Evidence summary: All candidate rows have blank ma_dc=True and blank inspection_id=True; certificate_nos=[MEDFAREASTLIQ&SEMISOL/2026/001, MEDFAREASTORAL/2026/001, MEDOFEORALB/2024/001]

### Candidate Details

- legacy_row_id=1217; certificate_no=MEDFAREASTORAL/2026/001; issue_date=2026-04-07 00:00:00+00:00; expiry_date=2028-07-17 00:00:00+00:00
- legacy_row_id=1244; certificate_no=MEDFAREASTLIQ&SEMISOL/2026/001; issue_date=2026-04-20 00:00:00+00:00; expiry_date=2028-07-19 00:00:00+00:00
- legacy_row_id=1348; certificate_no=MEDOFEORALB/2024/001; issue_date=2024-07-05 00:00:00+00:00; expiry_date=2026-12-15 00:00:00+00:00

## db.cc::GMP-129

- Projection: `current_certificate_projection`
- Source sheet: `db.cc`
- Business key: `GMP-129`
- Classification: `blank_ma_dc_non_case_backed_multi_current`
- Candidate legacy ids: `883, 1243, 1347`
- Current decision action: `no_winner`
- Review focus: Chon mot current certificate winner hoac xac nhan khong co winner khi cac dong khong co inspection/case backing.
- Decision question: Legacy certificate row nao phai dai dien cho current certificate projection cua site nay?
- Resolution rationale: Multiple non-case-backed certificate rows collapse onto one current key when MÃ DC is blank; no proven business discriminator exists yet.
- Evidence summary: All candidate rows have blank ma_dc=True and blank inspection_id=True; certificate_nos=[MED10/2020/001, MEDOFARINJC/2026/001, MEDOFEINJB/2024/001]

### Candidate Details

- legacy_row_id=883; certificate_no=MED10/2020/001; issue_date=2020-02-03 00:00:00+00:00; expiry_date=15-09-2020 (gia hạn đến 31-12-2023)
- legacy_row_id=1243; certificate_no=MEDOFARINJC/2026/001; issue_date=2026-04-07 00:00:00+00:00; expiry_date=2028-07-15 00:00:00+00:00
- legacy_row_id=1347; certificate_no=MEDOFEINJB/2024/001; issue_date=2024-07-05 00:00:00+00:00; expiry_date=2026-12-15 00:00:00+00:00

## db.cc::GMP-144

- Projection: `current_certificate_projection`
- Source sheet: `db.cc`
- Business key: `GMP-144`
- Classification: `blank_ma_dc_non_case_backed_multi_current`
- Candidate legacy ids: `1239, 1345, 1437, 1597`
- Current decision action: `no_winner`
- Review focus: Chon mot current certificate winner hoac xac nhan khong co winner khi cac dong khong co inspection/case backing.
- Decision question: Legacy certificate row nao phai dai dien cho current certificate projection cua site nay?
- Resolution rationale: Multiple non-case-backed certificate rows collapse onto one current key when MÃ DC is blank; no proven business discriminator exists yet.
- Evidence summary: All candidate rows have blank ma_dc=True and blank inspection_id=True; certificate_nos=[5130708009170, AG1100001001, INS-484520-103561370-20778606, NNGYK/GYSZ/11918-5/2024]

### Candidate Details

- legacy_row_id=1239; certificate_no=AG1100001001; issue_date=2023-10-04 00:00:00+00:00; expiry_date=2026-09-24 00:00:00+00:00
- legacy_row_id=1345; certificate_no=NNGYK/GYSZ/11918-5/2024; issue_date=2024-08-22 00:00:00+00:00; expiry_date=2027-04-07 00:00:00+00:00
- legacy_row_id=1437; certificate_no=INS-484520-103561370-20778606; issue_date=2025-09-02 00:00:00+00:00; expiry_date=05-2027
- legacy_row_id=1597; certificate_no=5130708009170; issue_date=2026-03-04 00:00:00+00:00; expiry_date=2029-03-03 00:00:00+00:00

## db.cc::GMP-2

- Projection: `current_certificate_projection`
- Source sheet: `db.cc`
- Business key: `GMP-2`
- Classification: `blank_ma_dc_non_case_backed_multi_current`
- Candidate legacy ids: `1241, 1598`
- Current decision action: `no_winner`
- Review focus: Chon mot current certificate winner hoac xac nhan khong co winner khi cac dong khong co inspection/case backing.
- Decision question: Legacy certificate row nao phai dai dien cho current certificate projection cua site nay?
- Resolution rationale: Multiple non-case-backed certificate rows collapse onto one current key when MÃ DC is blank; no proven business discriminator exists yet.
- Evidence summary: All candidate rows have blank ma_dc=True and blank inspection_id=True; certificate_nos=[NNGYK/30304-2/2026, OGYÉI/895-7/2023]

### Candidate Details

- legacy_row_id=1241; certificate_no=OGYÉI/895-7/2023; issue_date=2023-10-16 00:00:00+00:00; expiry_date=2026-05-01 00:00:00+00:00
- legacy_row_id=1598; certificate_no=NNGYK/30304-2/2026; issue_date=2026-04-16 00:00:00+00:00; expiry_date=2026-12-31 00:00:00+00:00

## db.cc::GMP-24

- Projection: `current_certificate_projection`
- Source sheet: `db.cc`
- Business key: `GMP-24`
- Classification: `blank_ma_dc_non_case_backed_multi_current`
- Candidate legacy ids: `835, 871, 1365, 1434`
- Current decision action: `no_winner`
- Review focus: Chon mot current certificate winner hoac xac nhan khong co winner khi cac dong khong co inspection/case backing.
- Decision question: Legacy certificate row nao phai dai dien cho current certificate projection cua site nay?
- Resolution rationale: Multiple non-case-backed certificate rows collapse onto one current key when MÃ DC is blank; no proven business discriminator exists yet.
- Evidence summary: All candidate rows have blank ma_dc=True and blank inspection_id=True; certificate_nos=[530-10/25-06/02; 381-13-08/256-25-06, DE_HE_01_GMP_2019_0065, DE_HE_01_GMP_2020_0081, DE_HE_01_GMP_2024_0239]

### Candidate Details

- legacy_row_id=835; certificate_no=DE_HE_01_GMP_2019_0065; issue_date=2019-05-13 00:00:00+00:00; expiry_date=2022-03-07 00:00:00+00:00
- legacy_row_id=871; certificate_no=DE_HE_01_GMP_2020_0081; issue_date=2020-06-03 00:00:00+00:00; expiry_date=07-03-2022 (gia hạn đến 31-12-2024)
- legacy_row_id=1365; certificate_no=DE_HE_01_GMP_2024_0239; issue_date=2024-11-05 00:00:00+00:00; expiry_date=2025-10-11 00:00:00+00:00
- legacy_row_id=1434; certificate_no=530-10/25-06/02; 381-13-08/256-25-06; issue_date=2025-07-18 00:00:00+00:00; expiry_date=2028-03-28 00:00:00+00:00

## db.cc::GMP-264

- Projection: `current_certificate_projection`
- Source sheet: `db.cc`
- Business key: `GMP-264`
- Classification: `blank_ma_dc_non_case_backed_multi_current`
- Candidate legacy ids: `1179, 1383`
- Current decision action: `no_winner`
- Review focus: Chon mot current certificate winner hoac xac nhan khong co winner khi cac dong khong co inspection/case backing.
- Decision question: Legacy certificate row nao phai dai dien cho current certificate projection cua site nay?
- Resolution rationale: Multiple non-case-backed certificate rows collapse onto one current key when MÃ DC is blank; no proven business discriminator exists yet.
- Evidence summary: All candidate rows have blank ma_dc=True and blank inspection_id=True; certificate_nos=[008/2023/RO, 098/2024/RO]

### Candidate Details

- legacy_row_id=1179; certificate_no=008/2023/RO; issue_date=2023-03-29 00:00:00+00:00; expiry_date=01-09-2024 (gia hạn đến 31/12/2024)
- legacy_row_id=1383; certificate_no=098/2024/RO; issue_date=2024-12-18 00:00:00+00:00; expiry_date=10/2027

## db.cc::GMP-337

- Projection: `current_certificate_projection`
- Source sheet: `db.cc`
- Business key: `GMP-337`
- Classification: `blank_ma_dc_non_case_backed_multi_current`
- Candidate legacy ids: `1330, 1451`
- Current decision action: `no_winner`
- Review focus: Chon mot current certificate winner hoac xac nhan khong co winner khi cac dong khong co inspection/case backing.
- Decision question: Legacy certificate row nao phai dai dien cho current certificate projection cua site nay?
- Resolution rationale: Multiple non-case-backed certificate rows collapse onto one current key when MÃ DC is blank; no proven business discriminator exists yet.
- Evidence summary: All candidate rows have blank ma_dc=True and blank inspection_id=True; certificate_nos=[ISF.405.105.2025.IP.1 WTC/0653_01_01/224, ISF.405.71.2024.IP.1 WTC/0653_01_01/129]

### Candidate Details

- legacy_row_id=1330; certificate_no=ISF.405.71.2024.IP.1 WTC/0653_01_01/129; issue_date=2024-07-02 00:00:00+00:00; expiry_date=2027-04-12 00:00:00+00:00
- legacy_row_id=1451; certificate_no=ISF.405.105.2025.IP.1 WTC/0653_01_01/224; issue_date=2025-09-17 00:00:00+00:00; expiry_date=2028-07-04 00:00:00+00:00

## db.cc::GMP-50

- Projection: `current_certificate_projection`
- Source sheet: `db.cc`
- Business key: `GMP-50`
- Classification: `blank_ma_dc_non_case_backed_multi_current`
- Candidate legacy ids: `839, 872, 889, 920, 1178, 1382`
- Current decision action: `no_winner`
- Review focus: Chon mot current certificate winner hoac xac nhan khong co winner khi cac dong khong co inspection/case backing.
- Decision question: Legacy certificate row nao phai dai dien cho current certificate projection cua site nay?
- Resolution rationale: Multiple non-case-backed certificate rows collapse onto one current key when MÃ DC is blank; no proven business discriminator exists yet.
- Evidence summary: All candidate rows have blank ma_dc=True and blank inspection_id=True; certificate_nos=[007/2023/RO, 097/2024/RO, DE_HE_01_GMP_2018_0017, DE_HE_01_GMP_2018_0127, DE_HE_01_GMP_2020_0072, II 23.2 (Bey) - 18/02(21)-B 55]

### Candidate Details

- legacy_row_id=839; certificate_no=II 23.2 (Bey) - 18/02(21)-B 55; issue_date=2018-07-06 00:00:00+00:00; expiry_date=2020-07-31 00:00:00+00:00
- legacy_row_id=872; certificate_no=DE_HE_01_GMP_2018_0017; issue_date=2018-02-07 00:00:00+00:00; expiry_date=2021-01-31 00:00:00+00:00
- legacy_row_id=889; certificate_no=DE_HE_01_GMP_2020_0072; issue_date=2020-05-18 00:00:00+00:00; expiry_date=2023-03-05 00:00:00+00:00
- legacy_row_id=920; certificate_no=DE_HE_01_GMP_2018_0127; issue_date=2018-10-24 00:00:00+00:00; expiry_date=31-12-2021 (gia hạn 31-12-2022)
- legacy_row_id=1178; certificate_no=007/2023/RO; issue_date=2023-03-29 00:00:00+00:00; expiry_date=01-09-2024 (gia hạn đến 31/12/2024)
- legacy_row_id=1382; certificate_no=097/2024/RO; issue_date=2024-12-18 00:00:00+00:00; expiry_date=10-2027

## db.cc::GMP-69

- Projection: `current_certificate_projection`
- Source sheet: `db.cc`
- Business key: `GMP-69`
- Classification: `blank_ma_dc_non_case_backed_multi_current`
- Candidate legacy ids: `1503, 1504, 1620`
- Current decision action: `no_winner`
- Review focus: Chon mot current certificate winner hoac xac nhan khong co winner khi cac dong khong co inspection/case backing.
- Decision question: Legacy certificate row nao phai dai dien cho current certificate projection cua site nay?
- Resolution rationale: Multiple non-case-backed certificate rows collapse onto one current key when MÃ DC is blank; no proven business discriminator exists yet.
- Evidence summary: All candidate rows have blank ma_dc=True and blank inspection_id=True; certificate_nos=[INS-484622-104529740-21440305, UK GMP 46387 Insp GMP 46387/14673770-0005, UK GMP 46387 Insp GMP 46387/15275896-0004]

### Candidate Details

- legacy_row_id=1503; certificate_no=UK GMP 46387 Insp GMP 46387/14673770-0005; issue_date=2026-01-07 00:00:00+00:00; expiry_date=2028-11-18 00:00:00+00:00
- legacy_row_id=1504; certificate_no=UK GMP 46387 Insp GMP 46387/15275896-0004; issue_date=2026-01-07 00:00:00+00:00; expiry_date=2028-11-18 00:00:00+00:00
- legacy_row_id=1620; certificate_no=INS-484622-104529740-21440305; issue_date=2026-03-26 00:00:00+00:00; expiry_date=2029-01-15 00:00:00+00:00
