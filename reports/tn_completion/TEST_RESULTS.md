# Test results (Task 18)

_Generated 2026-10-09T16:43:31 from saved artifacts by `ml/evaluation/build_completion_reports.py`._

`python -m pytest backend/tests --junitxml=reports/tn_completion/pytest.xml`

**86 tests · 0 failures · 0 errors · 0 skipped · 25.1 s**

| test | result |
|---|---|
| backend.tests.test_audit::test_every_category_quantified_and_either_priced_or_listed | PASSED |
| backend.tests.test_audit::test_doors_windows_counts_sizes_basis | PASSED |
| backend.tests.test_audit::test_quantity_formulas_and_amounts | PASSED |
| backend.tests.test_audit::test_no_silent_zero | PASSED |
| backend.tests.test_audit::test_report_traceability | PASSED |
| backend.tests.test_audit::test_other_elements_detected_not_ignored | PASSED |
| backend.tests.test_audit::test_land_separate_and_persisted | PASSED |
| backend.tests.test_audit::test_override_persists_and_locking | PASSED |
| backend.tests.test_boq::test_approved_requires_authority_date_reference | PASSED |
| backend.tests.test_boq::test_arithmetic_currency_and_status_validation | PASSED |
| backend.tests.test_boq::test_original_preserved_and_approved_grade | PASSED |
| backend.tests.test_boq::test_comparison_never_matches_incompatible_units_and_handles_zero | PASSED |
| backend.tests.test_boq::test_ambiguous_description_not_matched | PASSED |
| backend.tests.test_dataset_annotation::test_ingest_rejects_corrupt_and_tiny_and_is_idempotent | PASSED |
| backend.tests.test_dataset_annotation::test_restricted_sources_never_training_eligible | PASSED |
| backend.tests.test_dataset_annotation::test_split_routes_and_freezes_holdout | PASSED |
| backend.tests.test_dataset_annotation::test_annotation_validation | PASSED |
| backend.tests.test_dataset_annotation::test_annotation_double_review_and_export | PASSED |
| backend.tests.test_dataset_annotation::test_rejection_and_disagreement | PASSED |
| backend.tests.test_dataset_annotation::test_pseudo_labels_never_verified | PASSED |
| backend.tests.test_learning::test_confirmed_choice_is_reused_on_next_project | PASSED |
| backend.tests.test_learning::test_reference_boq_comparison_recorded | PASSED |
| backend.tests.test_legacy_migration::test_7_legacy_project_opens_with_unchanged_rates | PASSED |
| backend.tests.test_pipeline_quality::test_dedup_catches_resized_and_cropped_copies_not_other_drawings | PASSED |
| backend.tests.test_pipeline_quality::test_licence_rules | PASSED |
| backend.tests.test_pipeline_quality::test_leakage_checker_fails_on_planted_leak | PASSED |
| backend.tests.test_pipeline_quality::test_real_dataset_has_no_leakage | PASSED |
| backend.tests.test_pipeline_quality::test_opening_enrichment_and_conflict | PASSED |
| backend.tests.test_pipeline_quality::test_quality_checks_completeness_assumptions | PASSED |
| backend.tests.test_pipeline_quality::test_storey_count_required_and_room_area_error | PASSED |
| backend.tests.test_pipeline_quality::test_room_area_prefers_written_dimensions | PASSED |
| backend.tests.test_pipeline_quality::test_scale_parsing[SCALE 1:100-100-False] | PASSED |
| backend.tests.test_pipeline_quality::test_scale_parsing[SCALE = 1/50-50-False] | PASSED |
| backend.tests.test_pipeline_quality::test_scale_parsing[1:125-125-False] | PASSED |
| backend.tests.test_pipeline_quality::test_scale_parsing[NOT TO SCALE-None-True] | PASSED |
| backend.tests.test_pipeline_quality::test_scale_parsing[N.T.S-None-True] | PASSED |
| backend.tests.test_pipeline_quality::test_upload_validation_rejects_disguised_file | PASSED |
| backend.tests.test_pipeline_quality::test_registry_refuses_downgrade | PASSED |
| backend.tests.test_pipeline_quality::test_robots_wildcards_respected | PASSED |
| backend.tests.test_pipeline_quality::test_detector_model_is_working | PASSED |
| backend.tests.test_pipeline_quality::test_no_control_characters_in_source | PASSED |
| backend.tests.test_quantities_structural::test_area_definitions_are_distinct_and_traceable | PASSED |
| backend.tests.test_quantities_structural::test_assumed_scale_never_measured_and_missing_storeys_flagged | PASSED |
| backend.tests.test_quantities_structural::test_more_floor_labels[BASEMENT FLOOR PLAN-occ0] | PASSED |
| backend.tests.test_quantities_structural::test_more_floor_labels[LEVEL 5-occ1] | PASSED |
| backend.tests.test_quantities_structural::test_more_floor_labels[FLOORS 10-20-occ2] | PASSED |
| backend.tests.test_quantities_structural::test_terrace_is_not_a_storey | PASSED |
| backend.tests.test_quantities_structural::test_wall_quantities_formulas_and_status | PASSED |
| backend.tests.test_quantities_structural::test_steel_formula_and_no_invented_inputs | PASSED |
| backend.tests.test_quantities_structural::test_bbs_parsing_and_no_false_rows | PASSED |
| backend.tests.test_quantities_structural::test_structural_missing_and_schedule_members | PASSED |
| backend.tests.test_quantities_structural::test_site_plan_never_costed | PASSED |
| backend.tests.test_quantities_structural::test_mapping_review_unit_guard_and_priority | PASSED |
| backend.tests.test_quantities_structural::test_confidence_labels_and_estimate_never_high_when_incomplete | PASSED |
| backend.tests.test_quantities_structural::test_report_discloses_confidence_structure_areas | PASSED |
| backend.tests.test_quantities_structural::test_standard_data_approval_is_applied | PASSED |
| backend.tests.test_quantities_structural::test_review_fixes_regressions | PASSED |
| backend.tests.test_tn::test_only_tn_is_offered_and_resolved | PASSED |
| backend.tests.test_tn::test_other_states_rejected | PASSED |
| backend.tests.test_tn::test_non_tn_schedules_inactive | PASSED |
| backend.tests.test_tn::test_quantities_independent_of_location | PASSED |
| backend.tests.test_tn::test_rate_provenance_and_amendment | PASSED |
| backend.tests.test_tn::test_tnpwd_search | PASSED |
| backend.tests.test_tn::test_document_classifier | PASSED |
| backend.tests.test_tn::test_version_diff_and_amendment_apply | PASSED |
| backend.tests.test_tn::test_validator_rejects_bad_extraction | PASSED |
| backend.tests.test_tn::test_heading_strip | PASSED |
| backend.tests.test_tn::test_rate_analysis_units_and_additions | PASSED |
| backend.tests.test_tn::test_wastage_addition_not_applied_blindly | PASSED |
| backend.tests.test_tn::test_floor_occurrences[texts0-expect0] | PASSED |
| backend.tests.test_tn::test_floor_occurrences[texts1-expect1] | PASSED |
| backend.tests.test_tn::test_floor_occurrences[texts2-expect2] | PASSED |
| backend.tests.test_tn::test_floor_occurrences[texts3-expect3] | PASSED |
| backend.tests.test_tn::test_floor_occurrences[texts4-expect4] | PASSED |
| backend.tests.test_tn::test_floor_occurrences[texts5-expect5] | PASSED |
| backend.tests.test_tn::test_typical_without_numbers_and_no_false_floors | PASSED |
| backend.tests.test_tn::test_plan_multiplier_uses_occurrences | PASSED |
| backend.tests.test_tn::test_room_normalisation[TOIET-2-TOILET-2-toilet] | PASSED |
| backend.tests.test_tn::test_room_normalisation[TOLET-2-TOILET-2-toilet] | PASSED |
| backend.tests.test_tn::test_room_normalisation[BED ROOM-1 BEDRO-BED ROOM-1-bedroom] | PASSED |
| backend.tests.test_tn::test_room_normalisation[REFUGEAREA-REFUGE AREA-refuge] | PASSED |
| backend.tests.test_tn::test_room_normalisation[6'6\xb0WIDECORRIDOR-CORRIDOR-corridor] | PASSED |
| backend.tests.test_tn::test_room_normalisation[1711 Sft. 3BHK--unknown] | PASSED |
| backend.tests.test_tn::test_unit_grouping | PASSED |
| backend.tests.test_tn::test_feet_inch_dimensions | PASSED |
| backend.tests.test_tn::test_downscale_keeps_scale_in_caller_pixels | PASSED |
