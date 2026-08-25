# Unresolved FK Analysis

- raw_anomaly_count: 151
- confirmed_blanked_match_count: 151
- confirmed_blanked_match_failure_count: 0
- remaining_root_anomaly_count: 0
- cascade_anomaly_count: 2
- blank_fk_total: 149
- nonblank_dangling_fk_total: 2

## Blank FK Breakdown

- already_owner_confirmed_blanked: 149
- not_in_confirmed_blanked: 0

## Family Summary

| Family | Raw | Confirmed blanked | Remaining root | Cascade |
| --- | ---: | ---: | ---: | ---: |
| db.Tdoi / missing_site_fk | 22 | 22 | 0 | 0 |
| db.Tdoi2 / missing_change_request_fk | 2 | 2 | 0 | 1 |
| db.cc / missing_case_fk | 1 | 1 | 0 | 1 |
| db.cc / missing_site_fk | 26 | 26 | 0 | 0 |
| db.cso / missing_company_fk | 3 | 3 | 0 | 0 |
| db.dkkd / missing_site_fk | 50 | 50 | 0 | 0 |
| db.ktra / missing_site_fk | 47 | 47 | 0 | 0 |
