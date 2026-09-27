
/* ============================================================
   BSF Saudi Legal Case Workbench — Standard WebApp (JS component)

   Companion to backend.py and style.css. Responsibilities:
     * hold the whole translation catalogue ported from legal_ui.py,
       because the backend deliberately returns keys rather than
       localised labels;
     * render every view from the JSON the backend serves;
     * drive the async job endpoints and their progress reporting;
     * wire every button, form, upload, tab and search box.

   No business logic lives here. Every legal decision, persistence
   write and document render is a backend call.
   ============================================================ */

const I18N = {
  en: {
    "action_fallback": "Action",
    "accounting_analysis": "Accounting & forensic dispute analysis",
    "accounting_analysis_caption": "Reconcile account line items, build chronologies, detect number discrepancies, and synthesize forensic court findings.",
    "accounting_data_cleared": "Case accounting records cleared.",
    "accounting_instructions_label": "Analysis instructions (optional)",
    "accounting_instructions_placeholder": "e.g. Focus only on the disputed wire transfers; treat POS purchases as undisputed.",
    "accounting_response_label": "Accounting response",
    "financial_question_label": "Financial question",
    "claim_result_supported": "Supported",
    "claim_result_partially_supported": "Partially supported",
    "claim_result_contradicted": "Contradicted by evidence",
    "claim_result_not_verifiable": "Not verifiable",
    "claim_result_no_financial_evidence": "No financial evidence",
    "claim_result_not_financial_claim": "Not a financial claim",
    "all_reconciled": "All extracted transactions are reconciled across sources.",
    "classification_completed": "Document classification complete.",
    "classify_financial_documents": "1. Classify financial documents",
    "clear_accounting_data": "2. Clear accounting data (fresh start)",
    "column_amount": "Amount",
    "column_currency": "Currency",
    "column_description": "Description",
    "column_fin_date": "Date",
    "column_debit_credit": "Debit/Credit",
    "column_page": "Page",
    "column_row_status": "Status",
    "confirm_field": "Confirm {field}",
    "conflicts_require_review": "{count} item(s) require manual verification against source documents.",
    "correction_saved": "Correction saved.",
    "discrepancies_heading": "Categorized discrepancies & evidentiary citations",
    "documents_in_scope": "Documents in scope for extraction",
    "evidence_reference": "Evidence reference",
    "extraction_completed": "Completed. Reconciled {count} line item(s).",
    "findings_heading": "Forensic accounting findings for pleading draft",
    "forensic_timeline_caption": "Generate an authoritative audit chronology, cross-check discrepancies, and calculate mathematical loss models.",
    "forensic_timeline_discrepancy": "Forensic financial timeline & discrepancy analysis",
    "key_arguments_for_court": "Key arguments for court",
    "metric_bank_transfer_received": "Bank transfer received",
    "metric_disputed_freeze": "Disputed frozen sum",
    "metric_numbers_agreement": "Numbers agreement",
    "metric_total_inflows": "Total inflows (P2P sale)",
    "no_documents_selected": "Select at least one document.",
    "no_documents_stored": "No documents stored yet. Upload documents in the Documents tab first.",
    "no_value_selected": "Select a candidate value or enter a confirmed value.",
    "no_line_items": "No extracted line items available yet. Run extraction above.",
    "normalized_ledger": "Normalized financial ledger",
    "numbers_agree": "Agree (variance explained)",
    "numbers_disagree": "Disagreement detected",
    "or_confirmed_value": "Or confirmed {field}",
    "pipeline_configuration": "Pipeline configuration & reset controls",
    "recommended_defense_posture": "Recommended banking defense posture",
    "review_conflict_on_page": "Review conflict on page {page} (row {row})",
    "run_extraction_reconciliation": "Classify & extract financial data",
    "run_synthesis_hint": "Run the extraction above, then synthesize the timeline and findings.",
    "select_reading_for": "Select reading for {field}:",
    "synthesize_timeline_findings": "Synthesize timeline & forensic findings",
    "add_documents_or_evidence": "Add documents or evidence",
    "add_to_case_record": "Add my next message to the formal case record",
    "additional_instructions": "Additional attorney or client instructions",
    "agreement_answer_failed": "The grounded answer could not be prepared. Please try again.",
    "agreement_banking": "Banking agreement",
    "agreement_consultancy": "Consultancy agreement",
    "agreement_customer": "Customer agreement",
    "agreement_data_processing": "Data-processing agreement",
    "agreement_discussion": "Agreement discussion",
    "agreement_discussion_info": "Answers use the confirmed agreement, consolidated clauses, completed review, and retrieved knowledge-base authorities only. The dedicated Qwen 3.5 35B A3B model is used for this discussion.",
    "agreement_documents_processed": "Agreement documents were processed. Continue to classification.",
    "agreement_employment": "Employment agreement",
    "agreement_file_name": "Agreement file name",
    "agreement_files": "Agreement files",
    "agreement_library_caption": "Create or open an agreement-review file. Litigation actions and case pleadings are not shown here.",
    "agreement_list": "Agreement list",
    "agreement_name_or_reference": "Agreement name or reference",
    "agreement_nda": "NDA",
    "agreement_other": "Other agreement",
    "agreement_outsourcing": "Outsourcing agreement",
    "agreement_package": "Agreement package",
    "agreement_partnership": "Partnership agreement",
    "agreement_procurement": "Procurement agreement",
    "agreement_review_failed": "Agreement review failed: {error}",
    "agreement_review_library": "Agreement review library",
    "agreement_review_workflow": "Agreement review workflow",
    "agreement_software_licence": "Software/licence agreement",
    "agreement_tab_classification": "Classification",
    "agreement_tab_clause_map": "Clause map",
    "agreement_tab_discussion": "Discussion",
    "agreement_tab_package": "Agreement package",
    "agreement_tab_review": "Legal and commercial review",
    "agreement_type": "Agreement type",
    "agreement_upload_caption": "Upload one agreement or a package containing a master agreement, NDA, schedules, annexes, or service levels.",
    "agreement_vendor": "Vendor agreement",
    "also_affects_clauses": "Also affects related clause(s):",
    "amendment_placeholder": "Example: Add the missing chronology event, strengthen the objection to the fraud evidence, and revise request number 2.",
    "answer_format": "Answer format",
    "answer_format_arabic": "Arabic",
    "answer_format_both": "Arabic and English",
    "answer_format_english": "English",
    "app_caption": "Separate guided workspaces for litigation cases and agreement reviews, with knowledge-base-grounded analysis.",
    "app_title": "Saudi Legal Case Workbench",
    "applicable_law_research": "Applicable-law research and issue analysis",
    "approval_comments": "Approval comments / corrections recorded",
    "approve_consolidated_review": "Approve consolidated attorney review",
    "ask_about_case": "Ask about the case or propose a change to the current pleading",
    "ask_about_clause": "Ask about a clause, risk, law, or proposed amendment",
    "attorney_checks": "Attorney checks",
    "attorney_decision": "Attorney decision",
    "attorney_note": "Attorney note",
    "automatic_classification": "Automatic classification with attorney confirmation",
    "available_evidence": "Available evidence",
    "back_to_case_library": "Back to case library",
    "badge_ai_extracted": "AI-extracted",
    "badge_attorney_flagged": "Attorney-flagged",
    "badge_attorney_verified": "Attorney-verified",
    "badge_confidence": "Confidence {value}",
    "badge_confidence_high": "{source} · {value} confidence",
    "badge_confidence_low": "{source} · {value} · low confidence",
    "badge_confidence_review": "{source} · {value} · needs review",
    "badge_final": "Final",
    "badge_from_discussion": "From discussion",
    "badge_needs_review": "Needs review",
    "badge_provisional": "Provisional — pending dependency",
    "badge_unverified": "{source} · unverified",
    "basis_dated_source": "Dated source",
    "basis_inferred": "Inferred sequence — no dated source",
    "basis_source_no_date": "Source sequence without date",
    "block_case_dirty": "New case material was added — refresh and re-approve the attorney review before drafting.",
    "block_no_summary": "No attorney review has been prepared yet — do that in the attorney review tab first.",
    "block_not_approved": "The attorney review has not been approved yet — approve it in the attorney review tab.",
    "block_no_legal_analysis": "The legal analysis has not been completed yet — complete it before drafting the written pleading.",
    "block_accounting_incomplete": "The accounting analysis has not been completed yet — complete it before drafting the written pleading.",
    "card_agreement_review": "Agreement review",
    "card_attorney": "Attorney",
    "card_last_activity": "Last activity",
    "card_litigation_case": "Litigation case",
    "case_file_name": "Case file name",
    "case_journey": "Case journey",
    "case_journey_caption": "Completed work is restored automatically. New evidence reopens only the stages that require review.",
    "case_list": "Case list",
    "case_name_or_reference": "Case name or reference",
    "change_instruction": "Change instruction: ",
    "choose_workspace": "Choose workspace",
    "chronology_and_pages": "Chronology and original document pages",
    "chunk_progress": "Consolidation chunk {current}/{total} · {chunk_id}",
    "classification_caption": "The system proposes the document type and relationship from the extracted text. Nothing proceeds until you confirm or correct it.",
    "classification_confirmed": "Classification confirmed. Clause extraction is now unlocked.",
    "classification_failed": "Classification failed: {error}",
    "clause": "Clause",
    "clause_by_clause_review": "Clause-by-clause review",
    "clause_extraction_failed": "Clause extraction failed: {error}",
    "clause_map": "Clause map",
    "clause_map_metadata": "Processed {pages} page structures in {chunks} consolidation chunks. Interpretation is based on the package-wide consolidated map.",
    "clause_review_progress": "Clause review {current}/{total} · {clause_id}",
    "clauses": "Clauses",
    "column_chronology_basis": "Chronology basis",
    "column_date": "Date",
    "column_event": "Event",
    "column_evidence": "Evidence",
    "column_limitations": "Limitations",
    "column_name": "Name",
    "column_original_pages": "Original document pages",
    "column_related_evidence_pages": "Related evidence pages",
    "column_relevance": "Relevance",
    "column_role": "Role",
    "column_status": "Status",
    "compare_with_current": "Compare with current draft",
    "complete_review_first": "Complete the agreement review first to enable grounded clause discussion and redrafting.",
    "completeness_review": "Completeness review",
    "completeness_review_failed": "Completeness review failed: {error}",
    "conclusion_label": "Conclusion:",
    "confirm_classification": "Confirm classification",
    "confirm_classification_first": "Confirm the agreement type, relationship, and represented party first.",
    "consolidated_attorney_review": "Consolidated attorney review",
    "contradiction_caption": "These items may result from OCR, extraction, translation, or inconsistent source records. They are not treated as legal findings until an attorney verifies the original pages.",
    "correction_or_note": "Correction / note",
    "correction_placeholder": "Add a correction or note attorneys should see…",
    "counterparty": "Counterparty",
    "create_agreement_file": "Create agreement file",
    "create_agreement_review": "Create agreement review",
    "create_case_file": "Create case file",
    "create_litigation_case": "Create litigation case",
    "create_revised_version": "Create revised version",
    "critical_points_expander": "Critical points ({count})",
    "cross_clause_conflicts_expander": "Cross-clause conflicts ({count})",
    "cross_document_conflicts_expander": "Cross-document conflicts ({count})",
    "current_pleading_status": "Current pleading: version {version} · status: {status}",
    "decision_accept": "Accept",
    "decision_modify": "Modify",
    "decision_needs_instruction": "Needs client instruction",
    "decision_pending": "Pending",
    "decision_reject": "Reject",
    "default_agreement_name": "Agreement matter",
    "default_case_name": "Case",
    "defence_plan_locked": "Locked — approve the consolidated attorney review first (Attorney review tab).",
    "defence_planning_failed": "Defence planning failed: {error}",
    "defence_structure": "Defence structure",
    "detect_type_and_relationship": "Detect agreement type and relationship",
    "detected_with_confidence": "Detected with {value} confidence. Review and confirm below.",
    "detection_reasons": "Detection reasons:",
    "develop_defence_plan": "Develop defence plan",
    "discuss_this_case": "Discuss this case",
    "discussion_added_to_record": "A discussion message was explicitly added to the formal case record.",
    "discussion_caption": "Answers are generated only from this case record and the legal authorities retrieved from the knowledge base. Unsupported points are marked as insufficient; general LLM legal knowledge is not used.",
    "discussion_failed": "I recorded the question, but the case discussion request failed: {error}",
    "discussion_intro": "Use this space for questions and drafting guidance. Leave 'Add to formal case record' unchecked unless the message introduces a fact or evidence that should reopen the workflow.",
    "documents_already_stored": "{count} document(s) are already stored. Upload only new evidence or missing material.",
    "documents_and_evidence": "Documents and evidence",
    "documents_caption": "Upload all available material here. The system will extract, classify, and map it into the case record.",
    "docx_export_missing": "Word export needs `python-docx` in this code environment — add it to the environment's package list to enable this button.",
    "download_arabic_pleading": "Download Arabic pleading (.md)",
    "download_combined_pleading": "Download combined pleading (.docx)",
    "download_english_pleading": "Download English pleading (.md)",
    "enter_clear_file_name": "Enter a clear file name",
    "essential_case_summary": "Essential case summary",
    "event_fallback": "Event {number}",
    "exceptions_carve_outs": "Exceptions and carve-outs:",
    "exposure_sorted_caption": "All points are sorted by severity, regardless of category.",
    "extract_clause_map_first": "Extract the clause map first.",
    "extract_clauses": "Extract, consolidate, and organise clauses",
    "extracted_text_on_page": "Extracted text on this page",
    "facts_evidence_register": "Facts and evidence register",
    "facts_register_caption": "Every extracted fact, with how confident the extraction is and whether an attorney has verified it. Flag or correct items as you review, instead of leaving all corrections for one comment box at the end.",
    "file_purpose": "File purpose",
    "filter_clauses": "Filter by heading, number, or text",
    "filter_facts": "Filter facts",
    "final_approving_attorney": "Final approving attorney",
    "flag": "Flag",
    "flagged_for_review": "Flagged for review",
    "full_clause_text": "Full clause text",
    "generate_pleading": "Generate written pleading",
    "hit_chronology": "Chronology",
    "hit_discussion": "Discussion",
    "hit_evidence": "Evidence",
    "hit_fact": "Fact",
    "impact_level": "Impact level: ",
    "initial_pleading_draft": "Initial pleading draft",
    "item_fallback": "Item {number}",
    "iterative_attorney_review": "Iterative attorney review",
    "iterative_caption": "Discuss changes, regenerate a complete new version, compare versions, and mark the pleading final only after attorney approval.",
    "kb_authority_ids": "Knowledge-base authority IDs:",
    "kb_laws_and_authorities": "Knowledge-base laws and authorities",
    "kb_only_notice": "Knowledge-base-only mode: the analysis may use only laws and authority nodes retrieved from the configured knowledge base. Unsupported legal points remain unresolved and are sent for attorney review.",
    "kb_rules": "Knowledge-base rules:",
    "kind_bank_legal_risk": "Bank legal risk",
    "kind_decisive_gap": "Decisive legal gap",
    "kind_open_question": "Open legal question",
    "kind_weakens_position": "Weakens BSF position",
    "language": "Language",
    "legal_analysis_failed": "Legal analysis failed: {error}",
    "legal_exposure_and_position": "BSF legal exposure and position",
    "litigation_case_library": "Litigation case library",
    "litigation_files": "Litigation files",
    "litigation_library_caption": "Create or open a litigation file. Agreement classification and clause-review actions are not shown here.",
    "locked_reason": "Locked — {reason}",
    "main_parties": "Main parties",
    "mark_final": "Mark final",
    "material_contradictions": "Legally material contradictions",
    "metric_critical_points": "Critical points",
    "metric_cross_clause_conflicts": "Cross-clause conflicts",
    "metric_cross_document_conflicts": "Cross-document conflicts",
    "metric_documents": "Documents",
    "metric_facts": "Facts",
    "metric_issues": "Issues",
    "metric_kb_authorities": "KB authorities",
    "metric_missing_dependencies": "Missing dependencies",
    "metric_missing_protections": "Missing protections",
    "metric_missing_sections": "Missing/unclear sections",
    "metric_overall_posture": "Overall posture",
    "metric_pages": "Pages",
    "metric_parties": "Parties",
    "missing_dependencies_expander": "Missing dependencies ({count})",
    "missing_dependencies_provisional": "Missing dependencies keeping this provisional:",
    "missing_protections_expander": "Missing protections ({count})",
    "missing_sections_expander": "Missing or unclear sections ({count})",
    "narrative_checks_gaps": "The automated summary check found remaining gaps. Review before approval.",
    "narrative_checks_passed": "Automated narrative and BSF-risk completeness checks passed. Attorney verification is still required.",
    "negotiation_caption": "Generated directly from the review synthesis — nothing here is re-derived; it was already produced but not shown until now.",
    "negotiation_prep": "Negotiation prep",
    "new_material_uploaded": "New document or evidence was uploaded.",
    "next_analysis": "Run the legal analysis against the knowledge base",
    "next_documents": "Upload and process the case documents",
    "next_final": "Review the latest pleading and mark it final",
    "next_label": "Next: {action}",
    "next_pleading": "Generate the first written pleading",
    "next_review_new_material": "Review the newly added material before relying on earlier work",
    "next_summary": "Prepare and approve the consolidated attorney review",
    "no_arabic_summary": "A separate Arabic summary was not generated. Refresh the attorney summary.",
    "no_citable_rule": "No citable knowledge-base rule supports this issue; it remains unresolved.",
    "no_clause_text": "No text captured for this clause.",
    "no_dated_events": "No dated events were identified.",
    "no_english_summary": "A separate English summary was not generated. Refresh the attorney summary.",
    "no_evidence_recorded": "No evidence list was recorded in the current summary.",
    "no_exposure_points": "No legal exposure points recorded.",
    "no_facts_extracted": "No facts have been extracted yet. Process documents above first.",
    "no_matching_agreements": "No matching agreement files",
    "no_matching_cases": "No matching litigation cases",
    "no_material_contradiction": "No legally material contradiction affecting the bank's position was identified.",
    "no_negotiation_position": "No negotiation position was generated for this review yet — re-run the review above once clause reviews are available.",
    "no_pages_extracted": "No pages were extracted from {name}.",
    "no_parties_confirmed": "No parties were confirmed in the current summary.",
    "no_search_matches": "No matches yet — try a different term.",
    "no_summary_generated": "No consolidated summary has been generated in this session.",
    "no_verification_alerts": "No separate source-verification alerts were recorded.",
    "none_retrieved": "None retrieved",
    "note": "Note",
    "note_recorded": "Note recorded in the case audit log.",
    "open_agreement": "Open agreement",
    "open_case": "Open case",
    "open_destination": "Open **{destination}**.",
    "open_item_analysis": "Legal analysis",
    "open_item_gap": "Attorney review · gap",
    "open_item_question": "Attorney review · open question",
    "open_items_requiring_attention": "Open items requiring attention ({count})",
    "open_matter": "Open matter",
    "opponent_position": "Opponent's likely position:",
    "our_position": "Our position:",
    "page_image_load_failed": "{label} — could not load the rendered page image.",
    "page_image_unavailable": "Original page image is not available for this case.",
    "page_progress": "Page {page} of {total} — {state}",
    "page_rendering_quality": "Page rendering quality",
    "page_structure_progress": "Page structure {current}/{total} · {page_id}",
    "party_represented_by_us": "Party represented by us",
    "pleading_caption": "Generates a formal court-style pleading based on the attorney-approved record. Filing details and legal citations require final attorney verification.",
    "pleading_draft_notice": "Current state: working draft · Version {number}",
    "pleading_drafts_prepared": "The pleading drafts were prepared. Open the written pleading tab to review them.",
    "pleading_final_notice": "Final pleading approved by {name}. Reopen it before making further changes.",
    "pleading_generation_failed": "Written pleading generation failed: {error}",
    "pleading_instructions": "Pleading instructions",
    "pleading_instructions_placeholder": "Example: Prepare BSF's written defence, deny unsupported allegations, challenge the evidentiary basis, preserve procedural objections, and request dismissal or rejection of unsupported claims.",
    "pleading_intro": "Generate the first pleading, then revise it through versioned amendments until final attorney approval.",
    "pleading_revision_failed": "Pleading revision failed: {error}",
    "position_fallback": "Fallback positions",
    "position_high_priority": "High priority",
    "position_negotiable": "Negotiable",
    "position_non_negotiable": "Non-negotiable",
    "preferred_language": "Preferred language",
    "prepare_pleading": "Prepare written pleading",
    "prepare_refresh_summary": "Prepare / refresh attorney summary",
    "priority_label": "Priority: {value}",
    "process_agreement_documents": "Process agreement documents",
    "process_uploaded_pdfs": "Process uploaded PDFs",
    "processed_pages_of_file": "Processed {count} pages from {name}",
    "processing_file": "Processing {name}",
    "processing_summary": "Processed {files} document(s): {usable}/{total} usable pages. Added {facts} facts, {issues} issues, {parties} parties, {events} events and {requests} evidence requests.",
    "progress": "Progress",
    "provisional_dependency_caption": "A clause's conclusion stays provisional while a referenced definition, schedule, annex, or continuation is missing.",
    "provisional_findings_note": "{count} finding(s) remain provisional pending a missing dependency — see the badge on each clause below.",
    "purpose_contract": "Contract",
    "purpose_correspondence": "Correspondence",
    "purpose_decision": "Decision",
    "purpose_evidence": "Evidence",
    "purpose_full_case": "Full case file",
    "purpose_other": "Other",
    "question_for_client": "Question for the client: {question}",
    "questions_for_client": "Questions for the client",
    "recommended_action": "Recommended action: ",
    "redline_caption": "Redline: version {old} → version {new}. Green = added, red strikethrough = removed.",
    "related_clauses": "Related clauses:",
    "relationship_bank_customer": "Bank – customer",
    "relationship_bank_financial_institution": "Bank – financial institution",
    "relationship_bank_vendor": "Bank – vendor",
    "relationship_company_consultant": "Company – consultant",
    "relationship_employer_employee": "Employer – employee",
    "relationship_financial_institution_technology_provider": "Financial institution – technology provider",
    "relationship_institution_institution": "Institution – institution",
    "relationship_institution_service_provider": "Institution – service provider",
    "relationship_other": "Other relationship",
    "relationship_supplier_customer": "Supplier – customer",
    "relationship_type": "Relationship type",
    "reopen_final_pleading": "Reopen final pleading",
    "requested_amendment": "Requested amendment",
    "residual_risk_label": "Residual risk:",
    "response_label": "Response:",
    "restore_this_version": "Restore this version",
    "restored_from_version": "Restored from version {number}",
    "retrieve_laws_and_review": "Retrieve laws and review consolidated agreement",
    "review_and_correct_record": "Review and correct the generated record, then enter the attorney name and approve it.",
    "review_completeness": "Review completeness",
    "review_from_our_side": "Review from our side",
    "review_from_our_side_caption": "Commercial weaknesses are distinguished from legal findings. Legal findings use only retrieved knowledge-base authorities.",
    "review_objective": "Review objective and instructions",
    "review_objective_placeholder": "Protect payment, reduce liability, strengthen termination, regulatory compliance…",
    "reviewing_attorney_name": "Reviewing attorney name",
    "reviewing_clauses_status": "Reviewing each consolidated clause against targeted knowledge-base laws…",
    "run_analysis_hint": "Run legal analysis to connect the case problems to laws in the knowledge base.",
    "run_legal_analysis": "Run legal analysis",
    "save_note": "Save note",
    "search": "Search",
    "search_agreement_files": "Search agreement files",
    "search_inside_case": "Search inside the case",
    "search_litigation_cases": "Search litigation cases",
    "select_pdfs": "Select one or more PDFs",
    "severity_critical": "Critical",
    "severity_high": "High",
    "severity_low": "Low",
    "severity_medium": "Medium",
    "show_all_details": "Show all details",
    "show_all_details_help": "The compact view shows the highest-severity points first to reduce noise.",
    "showing_first_facts": "Showing the first 30 matching facts — narrow the filter to see more precisely.",
    "showing_matches": "Showing 25 of {total} matches.",
    "showing_matching_files": "Showing 8 of {total} matching files",
    "source_ids_label": "Source IDs:",
    "source_ids_used": "Source IDs:",
    "source_page": "Source page",
    "source_policy_kb_only": "Source policy: knowledge base only",
    "source_verification_alerts": "Source verification alerts",
    "start_by_preparing_review": "Start by preparing the review. Only the essential case summary will remain visible; supporting details will be available in closed sections.",
    "status_analysis": "Legal analysis",
    "status_default": "Intake",
    "status_final": "Final approved",
    "status_intake": "Document intake",
    "status_pleading": "Pleading preparation",
    "status_review": "Attorney review",
    "step_attorney_review": "Attorney review",
    "step_confirm_classification": "Confirm classification",
    "step_documents": "Documents",
    "step_final_approval": "Final approval",
    "step_legal_analysis": "Legal analysis",
    "step_map_clauses": "Map clauses",
    "step_review_and_amend": "Review and amend",
    "step_upload_agreement": "Upload agreement",
    "step_written_pleading": "Written pleading",
    "structuring_pages": "Structuring agreement pages and consolidating cross-page clauses…",
    "summary_approved_by_notice": "Approved by {name}. You can continue without repeating this step unless new evidence is added.",
    "summary_approved_unlocked": "Approved by {name} · {approval}. The pleading workflow is now unlocked.",
    "summary_check_caption": "The summary is checked for a coherent case story and BSF-specific risks before display. Supporting details stay closed for faster review.",
    "summary_generation_failed": "Attorney summary generation failed: {error}",
    "tab_accounting": "Accounting analysis",
    "tab_arabic": "Arabic",
    "tab_attorney_review": "Attorney review",
    "tab_case_discussion": "Case discussion",
    "tab_documents": "Documents",
    "tab_english": "English",
    "tab_home": "Home",
    "tab_legal_analysis": "Legal analysis",
    "tab_written_pleading": "Written pleading",
    "technical_case_details": "Technical case details",
    "technical_matter_details": "Technical matter details",
    "unassigned": "Unassigned",
    "uncertainties_heading": "Uncertainties",
    "unnamed_agreement": "Unnamed agreement",
    "unnamed_case": "Unnamed case",
    "unresolved_legal_issue": "Unresolved legal issue",
    "verified_this_session": "Verified this session",
    "verify": "Verify",
    "version_created": "Version {number} created.",
    "version_history": "Version history",
    "version_label": "Version {number}",
    "view_original_page_for": "View original page for",
    "weaknesses_identified": "Weaknesses identified:",
    "workspace": "Workspace",
    "workspace_agreements": "Agreement reviews",
    "workspace_litigation": "Litigation cases",
    "written_pleading": "Written pleading",
  },
  ar: {
    "action_fallback": "إجراء",
    "accounting_analysis": "التحليل المحاسبي والجنائي للنزاع",
    "accounting_analysis_caption": "تسوية بنود الحساب، وبناء التسلسل الزمني، واكتشاف الفروقات في الأرقام، وتوليف النتائج المحاسبية الجنائية للمرافعة.",
    "accounting_data_cleared": "تم مسح سجلات المحاسبة الخاصة بالقضية.",
    "accounting_instructions_label": "تعليمات التحليل (اختياري)",
    "accounting_instructions_placeholder": "مثال: ركّز فقط على التحويلات البنكية محل النزاع؛ اعتبر مشتريات نقاط البيع غير متنازع عليها.",
    "accounting_response_label": "الرد المحاسبي",
    "financial_question_label": "السؤال المالي",
    "claim_result_supported": "مدعوم",
    "claim_result_partially_supported": "مدعوم جزئياً",
    "claim_result_contradicted": "تناقضه الأدلة",
    "claim_result_not_verifiable": "غير قابل للتحقق",
    "claim_result_no_financial_evidence": "لا توجد أدلة مالية",
    "claim_result_not_financial_claim": "ليس مطلباً مالياً",
    "all_reconciled": "تمت تسوية جميع المعاملات المستخرجة عبر المصادر.",
    "classification_completed": "اكتمل تصنيف المستندات.",
    "classify_financial_documents": "١. تصنيف المستندات المالية",
    "clear_accounting_data": "٢. مسح بيانات المحاسبة (بداية جديدة)",
    "column_amount": "المبلغ",
    "column_currency": "العملة",
    "column_description": "الوصف",
    "column_fin_date": "التاريخ",
    "column_debit_credit": "مدين/دائن",
    "column_page": "الصفحة",
    "column_row_status": "الحالة",
    "confirm_field": "تأكيد {field}",
    "conflicts_require_review": "يتطلب {count} بند(ود) تحققاً يدوياً مقابل المستندات المصدرية.",
    "correction_saved": "تم حفظ التصحيح.",
    "discrepancies_heading": "الفروقات المصنفة والاستشهادات الإثباتية",
    "documents_in_scope": "المستندات المشمولة بالاستخراج",
    "evidence_reference": "مرجع الإثبات",
    "extraction_completed": "اكتمل. تمت تسوية {count} بند(ود).",
    "findings_heading": "النتائج المحاسبية الجنائية لمسودة المرافعة",
    "forensic_timeline_caption": "توليد تسلسل زمني موثق للتدقيق، والتحقق من الفروقات، وحساب نماذج الخسارة الحسابية.",
    "forensic_timeline_discrepancy": "التسلسل الزمني المالي الجنائي وتحليل الفروقات",
    "key_arguments_for_court": "الحجج الرئيسية أمام المحكمة",
    "metric_bank_transfer_received": "التحويل البنكي المستلم",
    "metric_disputed_freeze": "المبلغ المجمد محل النزاع",
    "metric_numbers_agreement": "اتفاق الأرقام",
    "metric_total_inflows": "إجمالي التدفقات (بيع فردي)",
    "no_documents_selected": "الرجاء اختيار مستند واحد على الأقل.",
    "no_documents_stored": "لا توجد مستندات مخزّنة بعد. يرجى رفع المستندات من تبويب المستندات أولاً.",
    "no_value_selected": "الرجاء اختيار قيمة مقترحة أو إدخال قيمة مؤكدة.",
    "no_line_items": "لا توجد بنود مستخرجة بعد. نفّذ الاستخراج أعلاه.",
    "normalized_ledger": "السجل المالي المُوحّد",
    "numbers_agree": "متفقة (تم تفسير الفارق)",
    "numbers_disagree": "تم اكتشاف تعارض",
    "or_confirmed_value": "أو قيمة {field} مؤكدة",
    "pipeline_configuration": "إعدادات خط المعالجة وأدوات إعادة الضبط",
    "recommended_defense_posture": "موقف الدفاع المصرفي الموصى به",
    "review_conflict_on_page": "مراجعة تعارض في الصفحة {page} (الصف {row})",
    "run_extraction_reconciliation": "تصنيف واستخراج البيانات المالية",
    "run_synthesis_hint": "نفّذ الاستخراج أعلاه، ثم قم بتوليف التسلسل الزمني والنتائج.",
    "select_reading_for": "اختر القراءة لـ {field}:",
    "synthesize_timeline_findings": "توليف التسلسل الزمني والنتائج الجنائية",
    "add_documents_or_evidence": "إضافة مستندات أو أدلة",
    "add_to_case_record": "أضف رسالتي التالية إلى سجل القضية الرسمي",
    "additional_instructions": "تعليمات إضافية من المحامي أو العميل",
    "agreement_answer_failed": "تعذر إعداد الإجابة الموثقة حالياً. يرجى إعادة المحاولة.",
    "agreement_banking": "اتفاقية مصرفية",
    "agreement_consultancy": "اتفاقية استشارية",
    "agreement_customer": "اتفاقية عميل",
    "agreement_data_processing": "اتفاقية معالجة بيانات",
    "agreement_discussion": "مناقشة الاتفاقية",
    "agreement_discussion_info": "تعتمد الإجابات على الاتفاقية المؤكدة والبنود الموحدة والمراجعة المكتملة ومراجع قاعدة المعرفة المستخرجة فقط. ويُستخدم نموذج Qwen 3.5 35B A3B المخصص لهذه المناقشة.",
    "agreement_documents_processed": "تمت معالجة مستندات الاتفاقية. انتقل إلى التصنيف.",
    "agreement_employment": "عقد عمل",
    "agreement_file_name": "اسم ملف الاتفاقية",
    "agreement_files": "ملفات الاتفاقيات",
    "agreement_library_caption": "أنشئ أو افتح ملف مراجعة اتفاقية. لا تظهر هنا إجراءات القضايا ولا المرافعات.",
    "agreement_list": "قائمة الاتفاقيات",
    "agreement_name_or_reference": "اسم الاتفاقية أو الرقم المرجعي",
    "agreement_nda": "اتفاقية عدم إفصاح",
    "agreement_other": "اتفاقية أخرى",
    "agreement_outsourcing": "اتفاقية تعهيد",
    "agreement_package": "حزمة الاتفاقيات",
    "agreement_partnership": "اتفاقية شراكة",
    "agreement_procurement": "اتفاقية مشتريات",
    "agreement_review_failed": "فشلت مراجعة الاتفاقية: {error}",
    "agreement_review_library": "مكتبة مراجعات الاتفاقيات",
    "agreement_review_workflow": "مسار مراجعة العقود والاتفاقيات",
    "agreement_software_licence": "اتفاقية برمجيات أو ترخيص",
    "agreement_tab_classification": "التصنيف",
    "agreement_tab_clause_map": "خريطة البنود",
    "agreement_tab_discussion": "المناقشة",
    "agreement_tab_package": "حزمة الاتفاقيات",
    "agreement_tab_review": "المراجعة القانونية والتجارية",
    "agreement_type": "نوع الاتفاقية",
    "agreement_upload_caption": "ارفع اتفاقية واحدة أو حزمة تتضمن اتفاقية إطارية أو اتفاقية عدم إفصاح أو جداول أو ملاحق أو مستويات خدمة.",
    "agreement_vendor": "اتفاقية مورد",
    "also_affects_clauses": "يؤثر أيضاً في بنود ذات صلة:",
    "amendment_placeholder": "مثال: أضف الواقعة الناقصة من التسلسل الزمني، وعزّز الاعتراض على دليل الاحتيال، وعدّل الطلب رقم 2.",
    "answer_format": "صيغة الإجابة",
    "answer_format_arabic": "العربية",
    "answer_format_both": "العربية والإنجليزية",
    "answer_format_english": "الإنجليزية",
    "app_caption": "مساحات عمل موجهة ومنفصلة لملفات القضايا ولمراجعات الاتفاقيات، مع تحليل مستند إلى قاعدة المعرفة.",
    "app_title": "منصة العمل للقضايا القانونية السعودية",
    "applicable_law_research": "بحث الأنظمة الواجبة التطبيق وتحليل المسائل",
    "approval_comments": "ملاحظات الاعتماد والتصحيحات المسجلة",
    "approve_consolidated_review": "اعتماد المراجعة الموحدة",
    "ask_about_case": "اسأل عن القضية أو اقترح تعديلاً على المرافعة الحالية",
    "ask_about_clause": "اسأل عن بند أو مخاطرة أو نظام أو تعديل مقترح",
    "attorney_checks": "فحوص المحامي",
    "attorney_decision": "قرار المحامي",
    "attorney_note": "ملاحظة المحامي",
    "automatic_classification": "التصنيف الآلي مع تأكيد المحامي",
    "available_evidence": "الأدلة المتاحة",
    "back_to_case_library": "العودة إلى المكتبة",
    "badge_ai_extracted": "مستخرج آلياً",
    "badge_attorney_flagged": "معلّم من المحامي",
    "badge_attorney_verified": "موثّق من المحامي",
    "badge_confidence": "درجة الثقة {value}",
    "badge_confidence_high": "{source} · ثقة {value}",
    "badge_confidence_low": "{source} · {value} · ثقة منخفضة",
    "badge_confidence_review": "{source} · {value} · يحتاج مراجعة",
    "badge_final": "نهائي",
    "badge_from_discussion": "من المناقشة",
    "badge_needs_review": "يحتاج مراجعة",
    "badge_provisional": "مبدئي — بانتظار اعتمادية",
    "badge_unverified": "{source} · غير موثق",
    "basis_dated_source": "مصدر مؤرخ",
    "basis_inferred": "تسلسل استدلالي بلا مصدر مؤرخ",
    "basis_source_no_date": "ترتيب مستند بلا تاريخ",
    "block_case_dirty": "أُضيفت مواد جديدة للقضية — حدّث المراجعة واعتمدها من جديد قبل الصياغة.",
    "block_no_summary": "لم تُعد مراجعة المحامي بعد — أعدّها أولاً من تبويب مراجعة المحامي.",
    "block_not_approved": "لم تُعتمد مراجعة المحامي بعد — اعتمدها من تبويب مراجعة المحامي.",
    "block_no_legal_analysis": "لم يكتمل التحليل القانوني بعد — أكمل التحليل القانوني قبل إعداد المذكرة.",
    "block_accounting_incomplete": "لم يكتمل التحليل المحاسبي بعد — أكمل التحليل المحاسبي قبل إعداد المذكرة.",
    "card_agreement_review": "مراجعة اتفاقية",
    "card_attorney": "المحامي",
    "card_last_activity": "آخر نشاط",
    "card_litigation_case": "قضية",
    "case_file_name": "اسم ملف القضية",
    "case_journey": "مسار القضية",
    "case_journey_caption": "يُستعاد العمل المكتمل تلقائياً. الأدلة الجديدة تعيد فتح المراحل التي تحتاج مراجعة فقط.",
    "case_list": "قائمة القضايا",
    "case_name_or_reference": "اسم القضية أو الرقم المرجعي",
    "change_instruction": "تعليمة التعديل: ",
    "choose_workspace": "اختر مساحة العمل",
    "chronology_and_pages": "التسلسل الزمني وصفحات المستندات الأصلية",
    "chunk_progress": "دفعة التوحيد {current}/{total} · {chunk_id}",
    "classification_caption": "يقترح النظام نوع المستند وطبيعة العلاقة من النص المستخرج. ولا يستمر أي إجراء قبل تأكيدك أو تصحيحك.",
    "classification_confirmed": "تم تأكيد التصنيف. أصبح استخراج البنود متاحاً.",
    "classification_failed": "فشل التصنيف: {error}",
    "clause": "بند",
    "clause_by_clause_review": "مراجعة البنود بنداً بنداً",
    "clause_extraction_failed": "فشل استخراج البنود: {error}",
    "clause_map": "خريطة البنود",
    "clause_map_metadata": "تمت معالجة {pages} هيكل صفحة في {chunks} دفعة توحيد. يستند التفسير إلى الخريطة الموحدة للحزمة كاملة.",
    "clause_review_progress": "مراجعة البند {current}/{total} · {clause_id}",
    "clauses": "البنود",
    "column_chronology_basis": "أساس الترتيب",
    "column_date": "التاريخ",
    "column_event": "الحدث",
    "column_evidence": "الدليل",
    "column_limitations": "القيود",
    "column_name": "الاسم",
    "column_original_pages": "صفحات المستند الأصلي",
    "column_related_evidence_pages": "صفحات الأدلة المرتبطة",
    "column_relevance": "الصلة",
    "column_role": "الصفة",
    "column_status": "الحالة",
    "compare_with_current": "مقارنة بالمسودة الحالية",
    "complete_review_first": "أكمل مراجعة الاتفاقية أولاً لتفعيل مناقشة البنود وإعادة صياغتها استناداً إلى المصادر.",
    "completeness_review": "مراجعة الاكتمال",
    "completeness_review_failed": "فشلت مراجعة الاكتمال: {error}",
    "conclusion_label": "النتيجة:",
    "confirm_classification": "تأكيد التصنيف",
    "confirm_classification_first": "أكّد نوع الاتفاقية والعلاقة والطرف الممثَّل أولاً.",
    "consolidated_attorney_review": "المراجعة الموحدة للمحامي",
    "contradiction_caption": "قد تنتج هذه العناصر عن التعرف الضوئي أو الاستخراج أو الترجمة أو تباين السجلات المصدرية. ولا تُعد نتائج قانونية حتى يتحقق المحامي من الصفحات الأصلية.",
    "correction_or_note": "تصحيح أو ملاحظة",
    "correction_placeholder": "أضف تصحيحاً أو ملاحظة يطّلع عليها المحامون…",
    "counterparty": "الطرف المقابل",
    "create_agreement_file": "إنشاء ملف الاتفاقية",
    "create_agreement_review": "إنشاء مراجعة اتفاقية",
    "create_case_file": "إنشاء ملف القضية",
    "create_litigation_case": "إنشاء ملف قضية",
    "create_revised_version": "إنشاء نسخة معدلة",
    "critical_points_expander": "نقاط حرجة ({count})",
    "cross_clause_conflicts_expander": "تعارضات بين البنود ({count})",
    "cross_document_conflicts_expander": "تعارضات بين المستندات ({count})",
    "current_pleading_status": "المرافعة الحالية: النسخة {version} · الحالة: {status}",
    "decision_accept": "قبول",
    "decision_modify": "تعديل",
    "decision_needs_instruction": "يحتاج تعليمات العميل",
    "decision_pending": "قيد الانتظار",
    "decision_reject": "رفض",
    "default_agreement_name": "ملف اتفاقية",
    "default_case_name": "قضية",
    "defence_plan_locked": "مقفل — اعتمد المراجعة الموحدة أولاً من تبويب مراجعة المحامي.",
    "defence_planning_failed": "فشل إعداد خطة الدفاع: {error}",
    "defence_structure": "هيكل الدفاع",
    "detect_type_and_relationship": "تحديد نوع الاتفاقية والعلاقة",
    "detected_with_confidence": "تم التحديد بدرجة ثقة {value}. راجع وأكّد أدناه.",
    "detection_reasons": "أسباب التحديد:",
    "develop_defence_plan": "إعداد خطة الدفاع",
    "discuss_this_case": "مناقشة القضية",
    "discussion_added_to_record": "أُضيفت رسالة مناقشة صراحةً إلى سجل القضية الرسمي.",
    "discussion_caption": "تُولَّد الإجابات من سجل هذه القضية والمراجع النظامية المستخرجة من قاعدة المعرفة فقط. وتُعلَّم النقاط غير المسندة بأنها غير كافية، ولا تُستخدم المعرفة القانونية العامة للنموذج.",
    "discussion_failed": "تم تسجيل السؤال، لكن طلب المناقشة أخفق: {error}",
    "discussion_intro": "استخدم هذه المساحة للأسئلة وتوجيه الصياغة. اترك خيار الإضافة إلى سجل القضية غير مفعّل ما لم تُدخل الرسالة واقعة أو دليلاً يستوجب إعادة فتح المسار.",
    "documents_already_stored": "يوجد {count} مستند مخزّن بالفعل. ارفع الأدلة الجديدة أو المواد الناقصة فقط.",
    "documents_and_evidence": "المستندات والأدلة",
    "documents_caption": "ارفع هنا كل المواد المتاحة. سيقوم النظام باستخراجها وتصنيفها وربطها بسجل القضية.",
    "docx_export_missing": "يتطلب التصدير إلى Word حزمة `python-docx` في بيئة التنفيذ — أضفها إلى قائمة حزم البيئة لتفعيل هذا الزر.",
    "download_arabic_pleading": "تنزيل المرافعة العربية (.md)",
    "download_combined_pleading": "تنزيل المرافعة الكاملة (.docx)",
    "download_english_pleading": "تنزيل المرافعة الإنجليزية (.md)",
    "enter_clear_file_name": "أدخل اسماً واضحاً للملف",
    "essential_case_summary": "الملخص الأساسي للقضية",
    "event_fallback": "الحدث {number}",
    "exceptions_carve_outs": "الاستثناءات:",
    "exposure_sorted_caption": "تُعرض جميع النقاط مرتبة حسب درجة الخطورة، بغض النظر عن نوعها.",
    "extract_clause_map_first": "استخرج خريطة البنود أولاً.",
    "extract_clauses": "استخراج البنود وتوحيدها وتنظيمها",
    "extracted_text_on_page": "النص المستخرج من هذه الصفحة",
    "facts_evidence_register": "سجل الوقائع والأدلة",
    "facts_register_caption": "كل واقعة مستخرجة مع درجة الثقة في استخراجها وما إذا كان المحامي قد وثّقها. علّم أو صحّح العناصر أثناء المراجعة بدلاً من تأجيل كل التصحيحات إلى مربع تعليق واحد في النهاية.",
    "file_purpose": "الغرض من الملف",
    "filter_clauses": "تصفية حسب العنوان أو الرقم أو النص",
    "filter_facts": "تصفية الوقائع",
    "final_approving_attorney": "المحامي المعتمد نهائياً",
    "flag": "تعليم",
    "flagged_for_review": "معلّم للمراجعة",
    "full_clause_text": "نص البند الكامل",
    "generate_pleading": "إنشاء المرافعة المكتوبة",
    "hit_chronology": "التسلسل الزمني",
    "hit_discussion": "المناقشة",
    "hit_evidence": "الدليل",
    "hit_fact": "واقعة",
    "impact_level": "درجة التأثير: ",
    "initial_pleading_draft": "المسودة الأولى للمرافعة",
    "item_fallback": "العنصر {number}",
    "iterative_attorney_review": "المراجعة التفاعلية للمحامي",
    "iterative_caption": "ناقش التعديلات، وأنشئ نسخة كاملة جديدة، وقارن بين النسخ، ولا تعتمد المرافعة نهائياً إلا بعد موافقة المحامي.",
    "kb_authority_ids": "معرّفات مراجع قاعدة المعرفة:",
    "kb_laws_and_authorities": "الأنظمة والمراجع من قاعدة المعرفة",
    "kb_only_notice": "وضع قاعدة المعرفة فقط: يستخدم التحليل الأنظمة والمراجع المستخرجة من قاعدة المعرفة المعتمدة فقط. وتبقى النقاط القانونية غير المسندة غير محسومة وتُحال إلى مراجعة المحامي.",
    "kb_rules": "القواعد من قاعدة المعرفة:",
    "kind_bank_legal_risk": "مخاطرة قانونية على البنك",
    "kind_decisive_gap": "نقص قانوني حاسم",
    "kind_open_question": "سؤال قانوني مفتوح",
    "kind_weakens_position": "يضعف موقف البنك",
    "language": "اللغة",
    "legal_analysis_failed": "فشل التحليل القانوني: {error}",
    "legal_exposure_and_position": "التعرض القانوني وموقف البنك",
    "litigation_case_library": "مكتبة ملفات القضايا",
    "litigation_files": "ملفات القضايا",
    "litigation_library_caption": "أنشئ أو افتح ملف قضية. لا تظهر هنا إجراءات تصنيف الاتفاقيات ولا مراجعة البنود.",
    "locked_reason": "مقفل — {reason}",
    "main_parties": "الأطراف الرئيسية",
    "mark_final": "اعتماد نهائي",
    "material_contradictions": "التعارضات ذات الأثر القانوني",
    "metric_critical_points": "نقاط حرجة",
    "metric_cross_clause_conflicts": "تعارضات بين البنود",
    "metric_cross_document_conflicts": "تعارضات بين المستندات",
    "metric_documents": "المستندات",
    "metric_facts": "الوقائع",
    "metric_issues": "المسائل",
    "metric_kb_authorities": "مراجع قاعدة المعرفة",
    "metric_missing_dependencies": "اعتماديات ناقصة",
    "metric_missing_protections": "حمايات غير موجودة",
    "metric_missing_sections": "أقسام ناقصة أو غير واضحة",
    "metric_overall_posture": "الموقف العام",
    "metric_pages": "الصفحات",
    "metric_parties": "الأطراف",
    "missing_dependencies_expander": "اعتماديات ناقصة ({count})",
    "missing_dependencies_provisional": "اعتماديات ناقصة تُبقي هذا البند مبدئياً:",
    "missing_protections_expander": "حمايات غير موجودة ({count})",
    "missing_sections_expander": "أقسام ناقصة أو غير واضحة ({count})",
    "narrative_checks_gaps": "كشف الفحص الآلي للملخص عن نواقص متبقية. راجعها قبل الاعتماد.",
    "narrative_checks_passed": "اجتازت الفحوص الآلية لترابط الرواية واكتمال مخاطر البنك. لا يزال توثيق المحامي مطلوباً.",
    "negotiation_caption": "مُولَّد مباشرة من خلاصة المراجعة — لا يُعاد اشتقاق أي شيء هنا؛ فقد أُنتج مسبقاً ولم يُعرض حتى الآن.",
    "negotiation_prep": "تحضير التفاوض",
    "new_material_uploaded": "تم رفع مستند أو دليل جديد.",
    "next_analysis": "شغّل التحليل القانوني بالاستناد إلى قاعدة المعرفة",
    "next_documents": "ابدأ برفع مستندات القضية ومعالجتها",
    "next_final": "راجع أحدث نسخة واعتمدها نهائياً",
    "next_label": "التالي: {action}",
    "next_pleading": "أنشئ المسودة الأولى للمرافعة",
    "next_review_new_material": "راجع المواد الجديدة قبل الاعتماد على العمل السابق",
    "next_summary": "أعد المراجعة الموحدة واعتمدها",
    "no_arabic_summary": "لم يتم إنشاء ملخص عربي مستقل. أعد إعداد ملخص المحامي.",
    "no_citable_rule": "لا توجد قاعدة قابلة للاستشهاد في قاعدة المعرفة تسند هذه المسألة؛ تبقى غير محسومة.",
    "no_clause_text": "لم يُلتقط نص لهذا البند.",
    "no_dated_events": "لم تُحدد أي أحداث مؤرخة.",
    "no_english_summary": "لم يتم إنشاء ملخص إنجليزي مستقل. أعد إعداد ملخص المحامي.",
    "no_evidence_recorded": "لم تُسجل قائمة أدلة في الملخص الحالي.",
    "no_exposure_points": "لا توجد نقاط تعرض قانوني مسجلة.",
    "no_facts_extracted": "لم تُستخرج أي وقائع بعد. عالج المستندات أعلاه أولاً.",
    "no_matching_agreements": "لا توجد ملفات اتفاقيات مطابقة",
    "no_matching_cases": "لا توجد قضايا مطابقة",
    "no_material_contradiction": "لم يتم تحديد تعارض جوهري يؤثر قانونياً في موقف البنك.",
    "no_negotiation_position": "لم يُنشأ موقف تفاوضي لهذه المراجعة بعد — أعد تشغيل المراجعة أعلاه بعد توفر مراجعات البنود.",
    "no_pages_extracted": "لم تُستخرج أي صفحات من {name}.",
    "no_parties_confirmed": "لم تُعتمد أي أطراف في الملخص الحالي.",
    "no_search_matches": "لا توجد نتائج مطابقة — جرّب مصطلحاً آخر.",
    "no_summary_generated": "لم يُنشأ ملخص موحد في هذه الجلسة.",
    "no_verification_alerts": "لا توجد تنبيهات تحقق منفصلة في الملخص الحالي.",
    "none_retrieved": "لم يُستخرج أي مرجع",
    "note": "ملاحظة",
    "note_recorded": "تم تسجيل الملاحظة في سجل تدقيق القضية.",
    "open_agreement": "فتح الاتفاقية",
    "open_case": "فتح القضية",
    "open_destination": "افتح **{destination}**.",
    "open_item_analysis": "التحليل القانوني",
    "open_item_gap": "مراجعة المحامي · نقص",
    "open_item_question": "مراجعة المحامي · سؤال مفتوح",
    "open_items_requiring_attention": "نقاط مفتوحة تحتاج إجراء ({count})",
    "open_matter": "ملف مفتوح",
    "opponent_position": "الموقف المرجح للخصم:",
    "our_position": "موقفنا:",
    "page_image_load_failed": "{label} — تعذر تحميل صورة الصفحة.",
    "page_image_unavailable": "صورة الصفحة الأصلية غير متاحة لهذا الملف.",
    "page_progress": "الصفحة {page} من {total} — {state}",
    "page_rendering_quality": "جودة عرض الصفحات",
    "page_structure_progress": "هيكلة الصفحة {current}/{total} · {page_id}",
    "party_represented_by_us": "الطرف الذي نمثله",
    "pleading_caption": "تُنشأ مرافعة رسمية بأسلوب المحاكم استناداً إلى السجل المعتمد من المحامي. وتتطلب بيانات الإيداع والاستشهادات النظامية تحققاً نهائياً من المحامي.",
    "pleading_draft_notice": "الحالة الراهنة: مسودة عمل · النسخة {number}",
    "pleading_drafts_prepared": "تم إعداد مسودات المرافعة. افتح تبويب المرافعة المكتوبة لمراجعتها.",
    "pleading_final_notice": "اعتُمدت المرافعة النهائية من {name}. أعد فتحها قبل إجراء أي تعديل إضافي.",
    "pleading_generation_failed": "فشل إنشاء المرافعة المكتوبة: {error}",
    "pleading_instructions": "تعليمات المرافعة",
    "pleading_instructions_placeholder": "مثال: أعدّ مذكرة دفاع البنك، وأنكر الادعاءات غير المسندة، واطعن في الأساس الإثباتي، واحتفظ بالدفوع الإجرائية، واطلب رد الدعوى أو رفض الطلبات غير المسندة.",
    "pleading_intro": "أنشئ المرافعة الأولى ثم عدّلها عبر نسخ متتابعة حتى الاعتماد النهائي من المحامي.",
    "pleading_revision_failed": "فشل تعديل المرافعة: {error}",
    "position_fallback": "مواقف بديلة",
    "position_high_priority": "أولوية عالية",
    "position_negotiable": "قابل للتفاوض",
    "position_non_negotiable": "غير قابل للتفاوض",
    "preferred_language": "اللغة المفضلة",
    "prepare_pleading": "إعداد المرافعة",
    "prepare_refresh_summary": "إعداد أو تحديث ملخص المحامي",
    "priority_label": "الأولوية: {value}",
    "process_agreement_documents": "معالجة مستندات الاتفاقية",
    "process_uploaded_pdfs": "معالجة الملفات المرفوعة",
    "processed_pages_of_file": "تمت معالجة {count} صفحة من {name}",
    "processing_file": "جارٍ معالجة {name}",
    "processing_summary": "تمت معالجة {files} مستنداً: {usable}/{total} صفحة قابلة للاستخدام. أُضيفت {facts} واقعة، و{issues} مسألة، و{parties} طرفاً، و{events} حدثاً، و{requests} طلب دليل.",
    "progress": "التقدم",
    "provisional_dependency_caption": "تبقى نتيجة البند مبدئية ما دام هناك تعريف أو جدول أو ملحق أو تكملة مشار إليها ومفقودة.",
    "provisional_findings_note": "تبقى {count} نتيجة مبدئية بانتظار اعتمادية ناقصة — انظر الشارة على كل بند أدناه.",
    "purpose_contract": "عقد",
    "purpose_correspondence": "مراسلات",
    "purpose_decision": "قرار",
    "purpose_evidence": "دليل",
    "purpose_full_case": "ملف القضية الكامل",
    "purpose_other": "أخرى",
    "question_for_client": "سؤال للعميل: {question}",
    "questions_for_client": "أسئلة للعميل",
    "recommended_action": "الإجراء المقترح: ",
    "redline_caption": "المقارنة: النسخة {old} ← النسخة {new}. الأخضر مضاف، والأحمر المشطوب محذوف.",
    "related_clauses": "بنود ذات صلة:",
    "relationship_bank_customer": "بنك – عميل",
    "relationship_bank_financial_institution": "بنك – مؤسسة مالية",
    "relationship_bank_vendor": "بنك – مورد",
    "relationship_company_consultant": "شركة – مستشار",
    "relationship_employer_employee": "صاحب عمل – موظف",
    "relationship_financial_institution_technology_provider": "مؤسسة مالية – مزود تقني",
    "relationship_institution_institution": "مؤسسة – مؤسسة",
    "relationship_institution_service_provider": "مؤسسة – مقدم خدمة",
    "relationship_other": "علاقة أخرى",
    "relationship_supplier_customer": "مورد – عميل",
    "relationship_type": "نوع العلاقة",
    "reopen_final_pleading": "إعادة فتح المرافعة النهائية",
    "requested_amendment": "التعديل المطلوب",
    "residual_risk_label": "المخاطر المتبقية:",
    "response_label": "الرد:",
    "restore_this_version": "استعادة هذه النسخة",
    "restored_from_version": "مستعادة من النسخة {number}",
    "retrieve_laws_and_review": "استخراج الأنظمة ومراجعة الاتفاقية الموحدة",
    "review_and_correct_record": "راجع السجل المُنشأ وصحّحه، ثم أدخل اسم المحامي واعتمده.",
    "review_completeness": "مراجعة الاكتمال",
    "review_from_our_side": "المراجعة من جانبنا",
    "review_from_our_side_caption": "تُميَّز نقاط الضعف التجارية عن النتائج القانونية. وتستند النتائج القانونية إلى مراجع قاعدة المعرفة المستخرجة فقط.",
    "review_objective": "هدف المراجعة وتعليمات المحامي",
    "review_objective_placeholder": "حماية الدفع، وتقليل المسؤولية، وتعزيز حق الإنهاء، والامتثال التنظيمي…",
    "reviewing_attorney_name": "اسم المحامي المراجع",
    "reviewing_clauses_status": "جارٍ مراجعة كل بند موحد مقابل الأنظمة المستهدفة من قاعدة المعرفة…",
    "run_analysis_hint": "شغّل التحليل القانوني لربط مسائل القضية بالأنظمة الموجودة في قاعدة المعرفة.",
    "run_legal_analysis": "تشغيل التحليل القانوني",
    "save_note": "حفظ الملاحظة",
    "search": "بحث",
    "search_agreement_files": "بحث في ملفات الاتفاقيات",
    "search_inside_case": "البحث داخل القضية",
    "search_litigation_cases": "بحث في ملفات القضايا",
    "select_pdfs": "اختر ملفاً أو أكثر بصيغة PDF",
    "severity_critical": "حرج",
    "severity_high": "مرتفع",
    "severity_low": "منخفض",
    "severity_medium": "متوسط",
    "show_all_details": "عرض جميع التفاصيل",
    "show_all_details_help": "يعرض العرض المختصر أهم النقاط لتقليل التشتيت.",
    "showing_first_facts": "عرض أول 30 واقعة مطابقة — ضيّق نطاق التصفية للحصول على نتائج أدق.",
    "showing_matches": "عرض 25 من {total} نتيجة.",
    "showing_matching_files": "عرض 8 من {total} ملفاً مطابقاً",
    "source_ids_label": "معرّفات المصادر:",
    "source_ids_used": "معرّفات المصادر:",
    "source_page": "صفحة المصدر",
    "source_policy_kb_only": "سياسة المصدر: قاعدة المعرفة فقط",
    "source_verification_alerts": "تنبيهات التحقق من المصدر",
    "start_by_preparing_review": "ابدأ بإعداد المراجعة. سيبقى الملخص الأساسي للقضية ظاهراً فقط، وتبقى التفاصيل المساندة في أقسام مغلقة.",
    "status_analysis": "التحليل القانوني",
    "status_default": "الاستلام",
    "status_final": "معتمد نهائياً",
    "status_intake": "استلام المستندات",
    "status_pleading": "إعداد المرافعة",
    "status_review": "مراجعة المحامي",
    "step_attorney_review": "مراجعة المحامي",
    "step_confirm_classification": "تأكيد التصنيف",
    "step_documents": "المستندات",
    "step_final_approval": "الاعتماد النهائي",
    "step_legal_analysis": "التحليل القانوني",
    "step_map_clauses": "استخراج البنود",
    "step_review_and_amend": "المراجعة والتعديل",
    "step_upload_agreement": "رفع الاتفاقية",
    "step_written_pleading": "المرافعة",
    "structuring_pages": "جارٍ هيكلة صفحات الاتفاقية وتوحيد البنود الممتدة بين الصفحات…",
    "summary_approved_by_notice": "اعتُمد من {name}. يمكنك المتابعة دون تكرار هذه الخطوة ما لم تُضف أدلة جديدة.",
    "summary_approved_unlocked": "اعتُمد من {name} · {approval}. أصبح مسار المرافعة متاحاً.",
    "summary_check_caption": "يُفحص الملخص للتأكد من ترابط رواية القضية ومن مخاطر البنك قبل عرضه. تبقى التفاصيل المساندة مغلقة لتسريع المراجعة.",
    "summary_generation_failed": "فشل إعداد ملخص المحامي: {error}",
    "tab_accounting": "التحليل المحاسبي والمالي",
    "tab_arabic": "العربية",
    "tab_attorney_review": "مراجعة المحامي",
    "tab_case_discussion": "مناقشة القضية",
    "tab_documents": "المستندات",
    "tab_english": "الإنجليزية",
    "tab_home": "الرئيسية",
    "tab_legal_analysis": "التحليل القانوني",
    "tab_written_pleading": "المرافعة المكتوبة",
    "technical_case_details": "البيانات التقنية للقضية",
    "technical_matter_details": "البيانات التقنية للملف",
    "unassigned": "غير مسند",
    "uncertainties_heading": "نقاط تحتاج إلى تحقق",
    "unnamed_agreement": "اتفاقية بدون اسم",
    "unnamed_case": "قضية بدون اسم",
    "unresolved_legal_issue": "مسألة قانونية غير محسومة",
    "verified_this_session": "موثّق في هذه الجلسة",
    "verify": "توثيق",
    "version_created": "أُنشئت النسخة {number}.",
    "version_history": "سجل النسخ",
    "version_label": "النسخة {number}",
    "view_original_page_for": "عرض الصفحة الأصلية لـ",
    "weaknesses_identified": "نقاط الضعف المحددة:",
    "workspace": "مساحة العمل",
    "workspace_agreements": "مراجعات العقود والاتفاقيات",
    "workspace_litigation": "القضايا والمرافعات",
    "written_pleading": "المرافعة المكتوبة",
  },
};
/* ============================================================
   Extra strings that exist only in the WebApp shell. Everything
   else comes from the catalogue ported from legal_ui.py above.
   ============================================================ */
Object.assign(I18N.en, {
  send: "Send",
  working: "Working…",
  loading: "Loading…",
  request_failed: "The request failed: {error}",
  detected_classification: "Detected classification",
  agreement_overview: "Agreement overview",
  clause_count: "{count} clauses",
  no_clauses: "No clauses have been extracted yet.",
  no_cases_open: "Open a matter from the library to begin.",
  confidence: "Confidence",
  page_label: "Page",
  compare_versions: "Compare versions",
  current_draft: "Current draft",
  files_queued: "{count} file(s) ready to process",
  no_files_selected: "Select at least one PDF first.",
  remove_file: "Remove",
  no_pages_usable: "{total} page(s) were read but none could be extracted, so no facts were added. Page status: {status}",
  extraction_reason: "Reason: {reason}",
});
Object.assign(I18N.ar, {
  send: "إرسال",
  working: "جارٍ التنفيذ…",
  loading: "جارٍ التحميل…",
  request_failed: "أخفق الطلب: {error}",
  detected_classification: "التصنيف المكتشف",
  agreement_overview: "نظرة عامة على الاتفاقية",
  clause_count: "{count} بنداً",
  no_clauses: "لم تُستخرج أي بنود بعد.",
  no_cases_open: "افتح ملفاً من المكتبة للبدء.",
  confidence: "درجة الثقة",
  page_label: "صفحة",
  compare_versions: "مقارنة النسخ",
  current_draft: "المسودة الحالية",
  files_queued: "{count} ملف جاهز للمعالجة",
  no_files_selected: "اختر ملف PDF واحداً على الأقل.",
  remove_file: "إزالة",
  no_pages_usable: "تمت قراءة {total} صفحة دون التمكن من استخراج أي منها، فلم تُضف أي وقائع. حالة الصفحات: {status}",
  extraction_reason: "السبب: {reason}",
});

/* Stage statuses, phases and the accounting review queue. */
Object.assign(I18N.en, {
  step_accounting: "Accounting analysis",
  step_discussion: "Case chatbot",
  status_not_started: "Not started",
  status_blocked: "Waiting on earlier steps",
  status_running: "Processing",
  status_waiting_for_user: "Waiting for you",
  status_ready: "Ready to continue",
  status_completed: "Completed",
  status_stale: "Needs refresh",
  status_error: "Error",
  phase_extracting_pages: "Extracting pages",
  phase_building_case_register: "Building the case register",
  phase_preparing_summary: "Preparing the attorney review",
  phase_classifying_pages: "Classifying pages",
  phase_extracting_financial_data: "Extracting financial data",
  phase_checking_review_items: "Checking values that need review",
  phase_building_timeline: "Building the financial timeline",
  phase_analysing_claims: "Comparing claims with the evidence",
  phase_researching_law: "Researching the applicable law",
  phase_planning_defence: "Preparing the defence plan",
  phase_generating_pleading: "Generating the written pleading",
  phase_revising_pleading: "Revising the written pleading",
  phase_answering: "Answering",
  detail_review_items: "{count} value(s) need your confirmation before the accounting analysis can continue.",
  detail_ready_for_analysis: "All extracted values are confirmed. Run the claims-vs-evidence analysis to continue.",
  detail_pages_classified: "Pages are classified. Run the extraction to continue.",
  detail_approve_summary: "The attorney review is prepared and waits for your approval.",
  detail_approved: "Attorney review approved.",
  detail_forensic_complete: "Financial claims compared with the reviewed ledger.",
  detail_complete_no_transactions: "No financial transactions were found in the selected documents.",
  detail_analysis: "Legal analysis ready.",
  detail_analysis_and_defence_plan: "Legal analysis and defence plan ready.",
  detail_draft: "Draft pleading ready.",
  detail_final: "Pleading marked final.",
  detail_inputs_missing: "Its inputs were changed or cleared. Regenerate it before relying on it.",
  detail_blocked_by: "Needs: {stages}",
  detail_stale_because: "Out of date: {stage} changed after this was produced.",
  attention_title: "Waiting for you",
  attention_error_title: "A step needs attention",
  attention_open: "Open {tab}",
  next_accounting: "Run the accounting extraction and confirm any flagged values",
  next_discussion: "Ask the case chatbot about the stored case record",
  next_waiting: "{stage} is waiting for you",
  next_error: "Retry the failed step: {stage}",
  clear_accounting_explainer: "Deletes this case's page classifications, extracted line items, your corrections, the normalized ledger, the financial timeline and the claim findings. Documents, the case register, the attorney review and the legal analysis are kept. A pleading built on this accounting is marked out of date.",
  review_items_heading: "Values waiting for your confirmation",
  review_item_title: "{page} — transaction row",
  review_issue_uncertain: "Uncertain reading",
  review_issue_missing: "Not found on the page",
  review_suggestion: "System's current interpretation",
  review_no_suggestion: "No value could be read",
  review_reasoning: "Why it needs you",
  review_row_as_printed: "Row as printed",
  review_page_excerpt: "Page context",
  review_transaction: "Transaction as understood so far",
  review_answer_placeholder: "Correct value for {field}",
  review_use_suggestion: "Confirm suggestion",
  review_save_answer: "Save answer",
  review_pending_marker: "awaiting you",
  field_date: "Date",
  field_amount: "Amount",
  field_currency: "Currency",
  field_debit_or_credit: "Debit / credit",
  field_description: "Description",
  field_reference_number: "Reference",
  field_party_source: "Party",
  field_running_balance: "Running balance",
  accounting_continue_auto: "All values confirmed — continuing the accounting analysis…",
  report_line: "{financial} of {scope} page(s) are financial · {rows} new row(s) extracted · {pending} value(s) awaiting you",
  report_failures: "{count} page(s) could not be processed. Run the extraction again to retry them.",
  report_discarded: "{count} zero-amount line(s) were ignored as balance or heading rows.",
  ledger_withheld: "{count} row(s) are withheld from the ledger until you confirm their values.",
  column_reference: "Reference",
  findings_run_meta: "Last run {at} · {claims} claim(s) from {source} · instructions: {instructions}",
  claims_source_attorney_review: "the attorney review",
  claims_source_case_register: "the case register",
  no_instructions: "none",
  case_register_heading: "Case register",
  case_register_caption: "The system's current understanding of the case, consolidated across every processed document. The attorney review, legal analysis, accounting claims and chatbot all read from it.",
  register_empty: "Nothing has been extracted yet. Process the case documents to build the register.",
  register_sources: "Built from {documents} document(s), {usable} of {pages} page(s) readable.",
  register_parties: "Parties",
  register_events: "Chronology",
  register_facts: "Facts",
  register_allegations: "Allegations",
  register_issues: "Issues",
  register_evidence_requests: "Evidence requests",
  register_contradictions: "Contradictions",
  register_none: "None recorded.",
  register_merged: "found in {count} places",
  register_clarify: "Needs clarification: {text}",
  register_questions: "Questions",
  fact_status_stated: "Stated",
  fact_status_alleged: "Alleged",
  fact_status_unclassified: "Unclassified",
  priority_high: "High priority",
  priority_critical: "Critical",
  priority_medium: "Medium priority",
  priority_low: "Low priority",
  expected_evidence_label: "Expected evidence",
  evidence_found_label: "Financial evidence found",
  missing_evidence_label: "Missing evidence",
  contradictions_label: "Contradictions and inconsistencies",
  comparison_label: "Comparison",
  none_found: "None found in the reviewed ledger.",
  none_identified: "None identified.",
  unverified_ids: "Cited by the model but not in the reviewed ledger (ignored): {ids}",
  stale_ids: "No longer in the ledger (accounting data changed after this analysis — rerun it): {ids}",
  claims_summary: "{count} claim(s) evaluated",
});
Object.assign(I18N.ar, {
  step_accounting: "التحليل المحاسبي",
  step_discussion: "مساعد القضية",
  status_not_started: "لم تبدأ",
  status_blocked: "بانتظار الخطوات السابقة",
  status_running: "قيد المعالجة",
  status_waiting_for_user: "بانتظارك",
  status_ready: "جاهزة للمتابعة",
  status_completed: "مكتملة",
  status_stale: "تحتاج إلى تحديث",
  status_error: "خطأ",
  phase_extracting_pages: "استخراج الصفحات",
  phase_building_case_register: "بناء سجل القضية",
  phase_preparing_summary: "إعداد مراجعة المحامي",
  phase_classifying_pages: "تصنيف الصفحات",
  phase_extracting_financial_data: "استخراج البيانات المالية",
  phase_checking_review_items: "فحص القيم التي تحتاج إلى مراجعة",
  phase_building_timeline: "بناء التسلسل الزمني المالي",
  phase_analysing_claims: "مقارنة المطالبات بالأدلة",
  phase_researching_law: "البحث في الأنظمة المنطبقة",
  phase_planning_defence: "إعداد خطة الدفاع",
  phase_generating_pleading: "إعداد المذكرة المكتوبة",
  phase_revising_pleading: "تعديل المذكرة المكتوبة",
  phase_answering: "إعداد الإجابة",
  detail_review_items: "{count} قيمة تحتاج إلى تأكيدك قبل متابعة التحليل المحاسبي.",
  detail_ready_for_analysis: "تم تأكيد جميع القيم المستخرجة. شغّل تحليل المطالبات مقابل الأدلة للمتابعة.",
  detail_pages_classified: "تم تصنيف الصفحات. شغّل الاستخراج للمتابعة.",
  detail_approve_summary: "مراجعة المحامي جاهزة وبانتظار اعتمادك.",
  detail_approved: "تم اعتماد مراجعة المحامي.",
  detail_forensic_complete: "تمت مقارنة المطالبات المالية بالسجل المالي المراجَع.",
  detail_complete_no_transactions: "لم يُعثر على معاملات مالية في المستندات المختارة.",
  detail_analysis: "التحليل القانوني جاهز.",
  detail_analysis_and_defence_plan: "التحليل القانوني وخطة الدفاع جاهزان.",
  detail_draft: "مسودة المذكرة جاهزة.",
  detail_final: "تم اعتماد المذكرة نهائياً.",
  detail_inputs_missing: "تغيّرت مدخلاتها أو حُذفت. أعد إنشاءها قبل الاعتماد عليها.",
  detail_blocked_by: "تتطلب: {stages}",
  detail_stale_because: "غير محدّثة: تغيّرت {stage} بعد إعدادها.",
  attention_title: "بانتظارك",
  attention_error_title: "خطوة تحتاج إلى متابعة",
  attention_open: "افتح {tab}",
  next_accounting: "شغّل الاستخراج المحاسبي وأكّد القيم المعلَّمة",
  next_discussion: "اسأل مساعد القضية عن سجل القضية المحفوظ",
  next_waiting: "{stage} بانتظارك",
  next_error: "أعد تشغيل الخطوة المتعثرة: {stage}",
  clear_accounting_explainer: "يحذف تصنيفات الصفحات والبنود المستخرجة وتصحيحاتك والسجل المالي الموحد والتسلسل الزمني ونتائج المطالبات لهذه القضية. تبقى المستندات وسجل القضية ومراجعة المحامي والتحليل القانوني كما هي، وتُعلَّم المذكرة المبنية على هذا التحليل بأنها غير محدّثة.",
  review_items_heading: "قيم بانتظار تأكيدك",
  review_item_title: "{page} — بند معاملة",
  review_issue_uncertain: "قراءة غير مؤكدة",
  review_issue_missing: "غير موجودة في الصفحة",
  review_suggestion: "التفسير الحالي للنظام",
  review_no_suggestion: "تعذّرت قراءة أي قيمة",
  review_reasoning: "سبب الحاجة إلى تأكيدك",
  review_row_as_printed: "البند كما ورد",
  review_page_excerpt: "سياق الصفحة",
  review_transaction: "المعاملة كما فُهمت حتى الآن",
  review_answer_placeholder: "القيمة الصحيحة لـ {field}",
  review_use_suggestion: "تأكيد الاقتراح",
  review_save_answer: "حفظ الإجابة",
  review_pending_marker: "بانتظارك",
  field_date: "التاريخ",
  field_amount: "المبلغ",
  field_currency: "العملة",
  field_debit_or_credit: "مدين / دائن",
  field_description: "الوصف",
  field_reference_number: "المرجع",
  field_party_source: "الطرف",
  field_running_balance: "الرصيد الجاري",
  accounting_continue_auto: "تم تأكيد جميع القيم — جارٍ متابعة التحليل المحاسبي…",
  report_line: "{financial} من {scope} صفحة مالية · {rows} بند جديد مستخرج · {pending} قيمة بانتظارك",
  report_failures: "تعذّرت معالجة {count} صفحة. شغّل الاستخراج مرة أخرى لإعادة المحاولة.",
  report_discarded: "تم تجاهل {count} سطر بمبلغ صفري باعتبارها أرصدة أو عناوين.",
  ledger_withheld: "{count} بند محجوب عن السجل المالي حتى تؤكد قيمه.",
  column_reference: "المرجع",
  findings_run_meta: "آخر تشغيل {at} · {claims} مطالبة من {source} · التعليمات: {instructions}",
  claims_source_attorney_review: "مراجعة المحامي",
  claims_source_case_register: "سجل القضية",
  no_instructions: "لا يوجد",
  case_register_heading: "سجل القضية",
  case_register_caption: "الفهم الحالي للقضية، موحداً من جميع المستندات المعالجة. تعتمد عليه مراجعة المحامي والتحليل القانوني والمطالبات المحاسبية ومساعد القضية.",
  register_empty: "لم يُستخرج شيء بعد. عالج مستندات القضية لبناء السجل.",
  register_sources: "مبني على {documents} مستند، {usable} من {pages} صفحة مقروءة.",
  register_parties: "الأطراف",
  register_events: "التسلسل الزمني",
  register_facts: "الوقائع",
  register_allegations: "الادعاءات",
  register_issues: "المسائل",
  register_evidence_requests: "الأدلة المطلوبة",
  register_contradictions: "التناقضات",
  register_none: "لا يوجد.",
  register_merged: "ورد في {count} مواضع",
  register_clarify: "يحتاج إلى توضيح: {text}",
  register_questions: "الأسئلة",
  fact_status_stated: "واقعة مذكورة",
  fact_status_alleged: "ادعاء",
  fact_status_unclassified: "غير مصنفة",
  priority_high: "أولوية عالية",
  priority_critical: "حرجة",
  priority_medium: "أولوية متوسطة",
  priority_low: "أولوية منخفضة",
  expected_evidence_label: "الأدلة المتوقعة",
  evidence_found_label: "الأدلة المالية الموجودة",
  missing_evidence_label: "الأدلة الناقصة",
  contradictions_label: "التناقضات وعدم الاتساق",
  comparison_label: "المقارنة",
  none_found: "لا توجد في السجل المالي المراجَع.",
  none_identified: "لم يُحدَّد شيء.",
  unverified_ids: "أشار إليها النموذج لكنها غير موجودة في السجل المراجَع (تم تجاهلها): {ids}",
  stale_ids: "لم تعد في السجل (تغيّرت البيانات المحاسبية بعد هذا التحليل — أعد تشغيله): {ids}",
  claims_summary: "تم تقييم {count} مطالبة",
});

const LANGUAGES = { en: "English", ar: "العربية" };

/// Added by Youssif for Monitoring Purposes ///
const SESSION_ID = (crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) + Math.random());
/// END ///

/* ============================================================
   Application state. One object, mutated by handlers, read by
   the render functions. Nothing else holds view state.
   ============================================================ */
const S = {
  lang: "en",
  workspace: "litigation",     // litigation | agreement_review
  view: "library",             // library | case | agreement
  tab: "home",
  agreementTab: "package",
  caseId: null,
  bootstrap: { logo: "", agreement_types: [], relationship_types: [] },
  snapshot: null,              // /case payload for the open matter
  cases: [],                   // library + sidebar list
  libraryQuery: "",
  caseQuery: "",
  factsFilter: "",
  clauseFilter: "",
  compareVersion: null,
  // A native <input type="file"> replaces its selection on every pick,
  // whereas the Streamlit uploader accumulated across picks. These queues
  // restore that behaviour: the input feeds them and is then cleared.
  uploads: { documents: [], agreement: [] },
  jobs: {},                    // region -> { detail, current, total }
  accountingSelectedDocs: null, // Set of case_document_id, lazily defaulted to "all" per case
};

/* ============================================================
   i18n
   ============================================================ */
function t(key, values) {
  const table = I18N[S.lang] || I18N.en;
  let text = table[key];
  if (text === undefined) text = (I18N.en[key] !== undefined ? I18N.en[key] : key);
  if (values) {
    text = text.replace(/\{(\w+)\}/g, (m, name) =>
      Object.prototype.hasOwnProperty.call(values, name) ? String(values[name]) : m);
  }
  return text;
}

function isRTL() { return S.lang === "ar"; }

function applyLanguage() {
  const root = document.getElementById("bsf-app");
  root.setAttribute("dir", isRTL() ? "rtl" : "ltr");
  document.documentElement.setAttribute("lang", S.lang);

  document.querySelectorAll("[data-i18n]").forEach((node) => {
    node.textContent = t(node.getAttribute("data-i18n"));
  });
  document.querySelectorAll(".bsf-seg-btn[data-lang]").forEach((btn) => {
    btn.classList.toggle("is-active", btn.getAttribute("data-lang") === S.lang);
  });

  // Placeholders that have no text node of their own.
  setPlaceholder("#library-search", S.workspace === "agreement_review"
    ? "search_agreement_files" : "search_litigation_cases");
  setPlaceholder("#case-search", "search_inside_case");
  setPlaceholder("#facts-filter", "filter_facts");
  setPlaceholder("#clause-filter", "filter_clauses");
  setPlaceholder('[data-form="ask"] input[name="question"]', "ask_about_case");
  setPlaceholder('[data-form="agreement-ask"] input[name="question"]', "ask_about_clause");
  setPlaceholder("#pleading-instructions", "pleading_instructions_placeholder");
  setPlaceholder('[data-form="confirm-classification"] textarea[name="review_objective"]',
    "review_objective_placeholder");
  setPlaceholder('[data-form="create-case"] input[name="case_name"]', "enter_clear_file_name");
  setPlaceholder("#accounting-instructions", "accounting_instructions_placeholder");
}

function setPlaceholder(selector, key) {
  const node = document.querySelector(selector);
  if (node) node.placeholder = t(key);
}

/* ============================================================
   DOM helpers
   ============================================================ */
const $ = (selector, scope) => (scope || document).querySelector(selector);
const $$ = (selector, scope) => Array.from((scope || document).querySelectorAll(selector));
const region = (name) => document.querySelector(`[data-region="${name}"]`);

function esc(value) {
  return String(value === null || value === undefined ? "" : value)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

function html(node, markup) { if (node) node.innerHTML = markup; }

function show(node, visible) { if (node) node.hidden = !visible; }

function badge(text, kind) {
  return `<span class="bsf-badge bsf-badge-${kind || "neutral"}">${esc(text)}</span>`;
}

function alertBox(text, kind) {
  return `<div class="bsf-alert bsf-alert-${kind || "info"}">${esc(text)}</div>`;
}

/* Minimal Markdown renderer, sufficient for the pleading markdown the
   backend produces (headings, bold, italics, ordered/unordered lists).
   The markdown itself is generated server-side by memo_to_markdown, so
   the wording and ordering stay byte-identical to the Streamlit build. */
function renderMarkdown(text) {
  const blocks = String(text || "").split(/\n{2,}/);
  const out = [];
  let listBuffer = [];
  const flush = () => {
    if (listBuffer.length) {
      out.push(`<ul>${listBuffer.join("")}</ul>`);
      listBuffer = [];
    }
  };
  blocks.forEach((raw) => {
    const block = raw.trim();
    if (!block) return;
    const inline = (s) => esc(s)
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/\*(.+?)\*/g, "<em>$1</em>")
      .replace(/`(.+?)`/g, "<code>$1</code>");
    const heading = block.match(/^(#{1,4})\s+(.*)$/);
    if (heading) {
      flush();
      const level = Math.min(heading[1].length + 1, 5);
      out.push(`<h${level}>${inline(heading[2])}</h${level}>`);
      return;
    }
    if (/^-\s+/.test(block)) {
      block.split("\n").forEach((line) => {
        listBuffer.push(`<li>${inline(line.replace(/^-\s+/, ""))}</li>`);
      });
      return;
    }
    flush();
    out.push(`<p>${inline(block).replace(/\n/g, "<br>")}</p>`);
  });
  flush();
  return out.join("");
}

/* Word-level redline used by the version comparison. */
function renderDiff(oldText, newText) {
  const a = String(oldText || "").split(/(\s+)/);
  const b = String(newText || "").split(/(\s+)/);
  const n = a.length, m = b.length;
  // Longest common subsequence table (inputs are a few thousand tokens).
  const lcs = Array.from({ length: n + 1 }, () => new Uint32Array(m + 1));
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      lcs[i][j] = a[i] === b[j] ? lcs[i + 1][j + 1] + 1 : Math.max(lcs[i + 1][j], lcs[i][j + 1]);
    }
  }
  const parts = [];
  let i = 0, j = 0;
  while (i < n && j < m) {
    if (a[i] === b[j]) { parts.push(esc(a[i])); i++; j++; }
    else if (lcs[i + 1][j] >= lcs[i][j + 1]) { parts.push(`<del class="bsf-diff-del">${esc(a[i])}</del>`); i++; }
    else { parts.push(`<ins class="bsf-diff-add">${esc(b[j])}</ins>`); j++; }
  }
  while (i < n) { parts.push(`<del class="bsf-diff-del">${esc(a[i++])}</del>`); }
  while (j < m) { parts.push(`<ins class="bsf-diff-add">${esc(b[j++])}</ins>`); }
  return parts.join("");
}

/* Plain text of a memo, used only to build the redline between two
   stored versions. On-screen rendering always uses the backend's own
   markdown so the displayed document is the authoritative one. */
function memoPlainText(memo, lang) {
  if (!memo) return "";
  const section = memo[lang === "ar" ? "pleading_ar" : "pleading_en"] || {};
  const chunks = [memo[lang === "ar" ? "title_ar" : "title_en"] || ""];
  const push = (value) => {
    if (!value) return;
    if (typeof value === "string") { chunks.push(value); return; }
    if (Array.isArray(value)) { value.forEach(push); return; }
    if (typeof value === "object") { Object.values(value).forEach(push); }
  };
  ["court_heading", "case_details", "party_heading", "subject", "opening", "facts",
   "procedural_defences", "substantive_defences", "response_to_opponent", "requests",
   "evidence_reservations", "reservations", "closing"].forEach((key) => push(section[key]));
  return chunks.filter(Boolean).join("\n\n");
}

/* ============================================================
   Backend transport

   Dataiku exposes getWebAppBackendUrl() to Standard WebApps. The
   fallback keeps the app usable when served directly during local
   development.
   ============================================================ */
function backendUrl(path) {
  if (typeof getWebAppBackendUrl === "function") return getWebAppBackendUrl(path);
  return path;
}

async function apiGet(path, params) {
  const p = params ? new URLSearchParams(params) : new URLSearchParams();
  p.append("_ts", Date.now()); // Cache-buster: forces the browser to get fresh data
  
  const response = await fetch(backendUrl(path) + "?" + p.toString(), { 
    headers: { Accept: "application/json" } 
  });
  return unwrap(response);
}

async function apiPost(path, body) {
  /// Added by Youssif for Monitoring Purposes ///
  const payload = Object.assign({}, body || {}, { session_id: SESSION_ID });
  /// END ///
  const response = await fetch(backendUrl(path), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    /// Added by Youssif for Monitoring Purposes ///
    //body: JSON.stringify(body || {}),
    body: JSON.stringify(payload),
    /// END ///
    
  });
  return unwrap(response);
}

async function apiUpload(path, formData) {
  /// Added by Youssif for Monitoring Purposes ///
  formData.append("session_id", SESSION_ID);
  /// END ///
  const response = await fetch(backendUrl(path), { method: "POST", body: formData });
  return unwrap(response);
}

async function apiText(path, params) {
  const query = params ? "?" + new URLSearchParams(params).toString() : "";
  const response = await fetch(backendUrl(path) + query);
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.text();
}

async function unwrap(response) {
  const body = await response.text();
  let payload = null;
  let parseFailed = false;
  if (body) {
    try { payload = JSON.parse(body); } catch (error) { parseFailed = true; }
  }
  if (!response.ok) {
    const message = (payload && payload.error) || `HTTP ${response.status}`;
    throw new Error(message);
  }
  if (parseFailed || payload === null) {
    // A 2xx whose body is not JSON. Report it here rather than returning
    // null and letting it surface as a property error deep in a renderer.
    const where = response.url ? response.url.split("?")[0].split("/").pop() : "backend";
    throw new Error(body
      ? `${where} returned unparseable JSON: ${body.slice(0, 160)}`
      : `${where} returned an empty response`);
  }
  return payload;
}

/* ============================================================
   Background jobs

   The backend runs extraction / LLM work in a worker thread and
   exposes progress at /job_status. It drops a finished job the
   first time its terminal status is read, so the result is taken
   from that same read.
   ============================================================ */
function jobMarkup(progress) {
  const { detail, current, total } = progress || {};
  const known = total > 0;
  const percent = known ? Math.round((current / total) * 100) : 0;
  return `
    <div class="bsf-job">
      <div class="bsf-job-detail">${esc(detail || t("working"))}</div>
      <div class="bsf-job-bar${known ? "" : " indet"}"><span style="width:${percent}%"></span></div>
    </div>`;
}

/* Poll one job until it ends. onProgress(status) runs on every running
   tick. Resolves with the job result, rejects with its error. */
function pollJob(jobId, onProgress) {
  return new Promise((resolve, reject) => {
    const poll = async () => {
      try {
        const status = await apiGet("/job_status", { job_id: jobId });
        if (status.status === "running") {
          if (onProgress) onProgress(status);
          setTimeout(poll, 1200);
          return;
        }
        if (status.status === "error") reject(new Error(status.error || "job failed"));
        else resolve(status.result || {});
      } catch (error) {
        reject(error);
      }
    };
    setTimeout(poll, 400);
  });
}

// Job ids this page is already polling, so a job started here is not
// polled twice when the case snapshot also reports it as running.
const FOLLOWED_JOBS = new Set();

function showStageProgress(stageKey, progress) {
  if (!stageKey) return;
  html(region(`stage-strip-${stageKey}`), stageRunningMarkup(stageKey, progress));
}

async function runJob(startPromise, regionName) {
  const target = region(regionName);
  html(target, jobMarkup({ detail: t("working") }));
  let jobId;
  try {
    const started = await startPromise;
    jobId = started.job_id;
  } catch (error) {
    html(target, "");
    throw error;
  }
  FOLLOWED_JOBS.add(jobId);
  try {
    return await pollJob(jobId, (status) => {
      html(target, jobMarkup(status.progress));
      showStageProgress(status.stage, status.progress);
    });
  } finally {
    FOLLOWED_JOBS.delete(jobId);
    html(target, "");
  }
}

/* A job may have been started from another tab or before a reload. The
   case snapshot lists running stages with their job id; follow them so
   the status strips stay live, then refresh when they finish. */
function followRunningJobs() {
  const caseId = S.caseId;
  ((S.snapshot && S.snapshot.stages) || []).forEach((stage) => {
    if (stage.status !== "running" || !stage.job_id || FOLLOWED_JOBS.has(stage.job_id)) return;
    FOLLOWED_JOBS.add(stage.job_id);
    pollJob(stage.job_id, (status) => showStageProgress(stage.key, status.progress))
      .catch(() => {})
      .finally(() => {
        FOLLOWED_JOBS.delete(stage.job_id);
        if (S.caseId === caseId) refreshCase();
      });
  });
}

/* ============================================================
   Toasts
   ============================================================ */
function toast(message, kind) {
  let host = document.getElementById("toasts");
  if (!host) {
    host = document.createElement("div");
    host.id = "toasts";
    host.className = "bsf-toasts";
    (document.getElementById("bsf-app") || document.body).appendChild(host);
  }
  const node = document.createElement("div");
  node.className = "bsf-toast" + (kind ? ` ${kind}` : "");
  node.textContent = message;
  host.appendChild(node);
  setTimeout(() => node.remove(), 5200);
}

function fail(error) {
  toast(t("request_failed", { error: error && error.message ? error.message : error }), "err");
}
/* ============================================================
   View + tab switching
   ============================================================ */
function showView(name) {
  S.view = name;
  $$("[data-view]").forEach((node) => node.classList.toggle("is-active", node.dataset.view === name));
}

function showTab(tabset, name) {
  const nav = document.querySelector(`[data-tabset="${tabset}"]`);
  if (!nav) return;
  const scope = nav.closest("[data-view]");
  $$("[data-tab]", nav).forEach((btn) => btn.classList.toggle("is-active", btn.dataset.tab === name));
  $$("[data-panel]", scope).forEach((panel) => panel.classList.toggle("is-active", panel.dataset.panel === name));
}

/* ============================================================
   Sidebar
   ============================================================ */
function renderSidebar() {
  const agreements = S.workspace === "agreement_review";

  $$("[data-workspace]").forEach((btn) => {
    btn.classList.toggle("is-active", btn.dataset.workspace === S.workspace);
  });

  const open = region("open-matter");
  if (S.snapshot) {
    show(open, true);
    region("chip-title").textContent = S.snapshot.display_name || t("open_matter");
    region("chip-ref").textContent = S.snapshot.reference;
  } else {
    show(open, false);
  }

  region("create-summary").textContent = t(agreements ? "create_agreement_review" : "create_litigation_case");
  region("create-name-label").textContent = t(agreements ? "agreement_file_name" : "case_file_name");
  region("create-submit").textContent = t(agreements ? "create_agreement_file" : "create_case_file");
}

function caseCardMarkup(item, compact) {
  const agreements = item.workflow_type === "agreement_review";
  const openLabel = t(agreements ? "open_agreement" : "open_case");
  const meta = compact ? "" : `
    <div class="case-card-meta">
      ${esc(t("card_attorney"))}: ${esc(item.attorney || t("unassigned"))}<br>
      ${esc(t("card_last_activity"))}: ${esc(item.activity || "—")}
    </div>
    ${item.status ? `<span class="status-pill">${esc(friendlyStatus(item.status))}</span>` : ""}`;
  return `
    <article class="case-card">
      <div class="case-card-title">${esc(item.title || t(agreements ? "unnamed_agreement" : "unnamed_case"))}</div>
      <div class="case-card-ref">${esc(item.reference)}</div>
      ${meta}
      <button type="button" class="bsf-btn" data-action="open-case" data-case-id="${esc(item.case_id)}">
        ${esc(openLabel)}
      </button>
    </article>`;
}

function friendlyStatus(status) {
  const key = String(status || "").trim().toLowerCase();
  const map = {
    intake: "status_intake", review: "status_review", analysis: "status_analysis",
    pleading: "status_pleading", final: "status_final",
  };
  return map[key] ? t(map[key]) : status;
}

/* ============================================================
   Case library
   ============================================================ */
function renderLibrary() {
  const agreements = S.workspace === "agreement_review";
  region("library-title").textContent = t(agreements ? "agreement_review_library" : "litigation_case_library");
  region("library-caption").textContent = t(agreements ? "agreement_library_caption" : "litigation_library_caption");

  const grid = region("library-grid");
  if (!S.cases.length) {
    html(grid, `<p class="bsf-caption">${esc(t(agreements ? "no_matching_agreements" : "no_matching_cases"))}</p>`);
    return;
  }
  html(grid, S.cases.map((item) => caseCardMarkup(item, false)).join(""));
}

async function loadCases() {
  try {
    const query = S.libraryQuery;
    const payload = await apiGet("/cases", { workflow: S.workspace, query });
    S.cases = payload.cases || [];
  } catch (error) {
    S.cases = [];
    fail(error);
  }
  renderSidebar();
  if (S.view === "library") renderLibrary();
}

/* ============================================================
   Matter loading
   ============================================================ */
async function openCase(caseId) {
  try {
    const snapshot = await apiGet("/case", { case_id: caseId });
    if (!snapshot || !snapshot.case_id) throw new Error("the case snapshot came back empty");
    S.caseId = caseId;
    S.snapshot = snapshot;
    S.compareVersion = null;
    S.accountingSelectedDocs = null;
    // Every matter opens on its first tab, whatever was selected last time.
    S.tab = "home";
    S.agreementTab = "package";
    if (snapshot.workflow_type === "agreement_review") {
      S.workspace = "agreement_review";
      showView("agreement");
      showTab("agreement", S.agreementTab);
      renderAgreement();
    } else {
      S.workspace = "litigation";
      showView("case");
      showTab("case", S.tab);
      renderCase();
    }
    renderSidebar();
  } catch (error) {
    fail(error);
  }
}

async function refreshCase() {
  if (!S.caseId) return;
  try {
    const snapshot = await apiGet("/case", { case_id: S.caseId });
    if (!snapshot || !snapshot.case_id) throw new Error("the case snapshot came back empty");
    S.snapshot = snapshot;
    if (S.snapshot.workflow_type === "agreement_review") renderAgreement();
    else renderCase();
  } catch (error) {
    fail(error);
  }
}

function backToLibrary() {
  S.caseId = null;
  S.snapshot = null;
  showView("library");
  renderSidebar();
  loadCases();
}

/* ============================================================
   Litigation matter — shared header + Home
   ============================================================ */
const STAGE_LABEL_KEYS = {
  documents: "step_documents", review: "step_attorney_review", accounting: "step_accounting",
  analysis: "step_legal_analysis", pleading: "step_written_pleading", discussion: "step_discussion",
};
const STAGE_TAB_KEYS = {
  documents: "tab_documents", review: "tab_attorney_review", accounting: "tab_accounting",
  analysis: "tab_legal_analysis", pleading: "tab_written_pleading", discussion: "tab_case_discussion",
};
const NEXT_ACTION_KEYS = {
  documents: "next_documents", review: "next_summary", accounting: "next_accounting",
  analysis: "next_analysis", pleading: "next_pleading", discussion: "next_discussion",
};
const STAGE_STATUS_KIND = {
  not_started: "neutral", blocked: "neutral", running: "ai", waiting_for_user: "review",
  ready: "provisional", completed: "verified", stale: "review", error: "flagged",
};
const STAGE_ICONS = {
  completed: "\u2713", running: "\u21BB", waiting_for_user: "!", error: "\u2715",
  stale: "\u21BA", ready: "\u25CF", not_started: "\u25CB", blocked: "\u25CB",
};

function stageLabel(key) { return t(STAGE_LABEL_KEYS[key] || key); }

function stageByKey(key) {
  return ((S.snapshot && S.snapshot.stages) || []).find((stage) => stage.key === key);
}

function stageDetailText(stage) {
  if (stage.status === "error") return stage.error || "";
  if (stage.status === "waiting_for_user" && stage.detail === "review_items") {
    const acc = (S.snapshot && S.snapshot.accounting) || {};
    return t("detail_review_items", { count: acc.pending_field_count || acc.pending_count || 0 });
  }
  if (stage.status === "stale" && stage.stale_because) {
    return t("detail_stale_because", { stage: stageLabel(stage.stale_because) });
  }
  if (stage.status === "blocked" && (stage.blocked_by || []).length) {
    return t("detail_blocked_by", { stages: stage.blocked_by.map(stageLabel).join(", ") });
  }
  if (stage.detail) {
    const key = `detail_${stage.detail}`;
    const text = t(key);
    return text !== key ? text : stage.detail;
  }
  return "";
}

function stageRunningMarkup(stageKey, progress) {
  const phase = progress && progress.phase ? t(`phase_${progress.phase}`) : t("status_running");
  return `
    <div class="bsf-stage-strip status-running">
      <div class="bsf-stage-strip-head">${badge(t("status_running"), "ai")}<strong>${esc(phase)}</strong></div>
      ${jobMarkup(progress)}
    </div>`;
}

function stageStripMarkup(stage) {
  if (!stage) return "";
  if (stage.status === "running") {
    return stageRunningMarkup(stage.key, stage.progress || { phase: stage.phase, detail: stage.detail });
  }
  const detail = stageDetailText(stage);
  return `
    <div class="bsf-stage-strip status-${esc(stage.status)}">
      <div class="bsf-stage-strip-head">
        ${badge(t(`status_${stage.status}`), STAGE_STATUS_KIND[stage.status])}
        <strong>${esc(stageLabel(stage.key))}</strong>
      </div>
      ${detail ? `<div class="bsf-stage-strip-detail">${esc(detail)}</div>` : ""}
    </div>`;
}

function renderStageStrips() {
  Object.keys(STAGE_LABEL_KEYS).forEach((key) => {
    html(region(`stage-strip-${key}`), stageStripMarkup(stageByKey(key)));
  });
}

/* Case-wide banner above the tabs: anything waiting for the user, and any
   failed step, is visible from every tab. */
function renderAttention() {
  const snap = S.snapshot;
  const stages = snap.stages || [];
  const line = (stage) => `
    <li>
      <span><strong>${esc(stageLabel(stage.key))}</strong> — ${esc(stageDetailText(stage) || t(`status_${stage.status}`))}</span>
      <button type="button" class="bsf-btn" data-action="goto-stage" data-stage="${esc(stage.key)}">
        ${esc(t("attention_open", { tab: t(STAGE_TAB_KEYS[stage.key]) }))}
      </button>
    </li>`;
  const waiting = stages.filter((stage) => stage.status === "waiting_for_user");
  const errors = stages.filter((stage) => stage.status === "error");
  html(region("case-attention"), `
    ${waiting.length ? `
      <div class="bsf-attention" role="alert">
        <div class="bsf-attention-title">${esc(t("attention_title"))}</div>
        <ul>${waiting.map(line).join("")}</ul>
      </div>` : ""}
    ${errors.length ? `
      <div class="bsf-attention is-error" role="alert">
        <div class="bsf-attention-title">${esc(t("attention_error_title"))}</div>
        <ul>${errors.map(line).join("")}</ul>
      </div>` : ""}`);
}

function renderCase() {
  const snap = S.snapshot;
  if (!snap) return;
  region("case-title").textContent = snap.display_name || t("default_case_name");
  region("case-ref").textContent = snap.reference;

  const dirty = region("case-dirty");
  const state = snap.workflow_state || {};
  if (state.case_dirty) {
    dirty.textContent = state.dirty_reason || t("next_review_new_material");
    show(dirty, true);
  } else {
    show(dirty, false);
  }

  renderAttention();
  renderStageStrips();
  renderCaseStatus();
  renderUnresolved();
  renderCaseSearch();
  renderDocumentsTab();
  renderCaseRegister();
  renderAccountingTab();
  renderReviewTab();
  renderAnalysisTab();
  renderPleadingTab();
  renderDiscussionTab();
  followRunningJobs();
}

function renderCaseStatus() {
  const snap = S.snapshot;
  const stages = snap.stages || [];
  const done = stages.filter((stage) => stage.status === "completed").length;
  const percent = stages.length ? Math.round((done / stages.length) * 100) : 0;

  const nextKey = snap.next_stage || "documents";
  const nextStage = stageByKey(nextKey) || { status: "" };
  let nextText;
  if (nextStage.status === "waiting_for_user") nextText = t("next_waiting", { stage: stageLabel(nextKey) });
  else if (nextStage.status === "error") nextText = t("next_error", { stage: stageLabel(nextKey) });
  else nextText = t(NEXT_ACTION_KEYS[nextKey] || "next_documents");
  const destination = t(STAGE_TAB_KEYS[nextKey] || "tab_documents");

  const stepCards = stages.map((stage) => `
    <button type="button" class="step-card ${stage.state} status-${esc(stage.status)}"
            data-action="goto-stage" data-stage="${esc(stage.key)}">
      <div class="step-icon">${STAGE_ICONS[stage.status] || ""}</div>
      <div class="step-label">${esc(stageLabel(stage.key))}</div>
      <div class="step-status">${esc(stage.status === "running" && stage.phase ? t(`phase_${stage.phase}`) : t(`status_${stage.status}`))}</div>
    </button>`).join("");

  const counts = snap.counts || {};
  const metric = (key, value) => `
    <div class="bsf-metric">
      <span class="m-value">${esc(value)}</span>
      <span class="m-label">${esc(t(key))}</span>
    </div>`;

  html(region("case-status"), `
    <div class="bsf-status">
      <div class="bsf-status-head">
        <h4>${esc(t("case_journey"))}</h4>
        <div class="bsf-metric">
          <span class="m-value">${percent}%</span>
          <span class="m-label">${esc(t("progress"))}</span>
        </div>
      </div>
      <p class="bsf-caption">${esc(t("case_journey_caption"))}</p>
      <div class="bsf-progressbar"><span style="width:${percent}%"></span></div>
      <div class="bsf-steps">${stepCards}</div>
      <div class="bsf-status-meta">
        <div class="bsf-next">
          <strong>${esc(t("next_label", { action: nextText }))}</strong>
          <em>${esc(t("open_destination", { destination }).replace(/\*\*/g, ""))}</em>
        </div>
        ${metric("metric_documents", counts.documents || 0)}
        ${metric("metric_pages", counts.pages || 0)}
        ${metric("metric_facts", counts.facts || 0)}
        ${metric("metric_parties", counts.parties || 0)}
        ${metric("metric_issues", counts.issues || 0)}
      </div>
    </div>`);
}

function renderUnresolved() {
  const snap = S.snapshot;
  const state = snap.workflow_state || {};
  const items = [];

  const analysis = state.analysis || {};
  (analysis.issues || []).forEach((issue) => {
    if (String(issue.conclusion || "").toLowerCase() === "unresolved") {
      items.push({ kind: t("open_item_analysis"), label: issue.issue_title || t("unresolved_legal_issue") });
    }
  });
  const summary = state.attorney_summary || {};
  (summary.bank_gaps || []).forEach((gap) => {
    const label = isRTL() ? gap.gap_ar : gap.gap_en;
    if (label) items.push({ kind: t("open_item_gap"), label });
  });
  (summary.bank_legal_questions || []).forEach((question) => {
    const label = isRTL() ? question.question_ar : question.question_en;
    if (label) items.push({ kind: t("open_item_question"), label });
  });

  const target = region("unresolved-tracker");
  if (!items.length) { html(target, ""); return; }
  html(target, `
    <details class="bsf-expander">
      <summary>${esc(t("open_items_requiring_attention", { count: items.length }))}</summary>
      <div class="bsf-expander-body">
        ${items.map((item) => `
          <div class="bsf-item">
            ${badge(item.kind, "review")}
            <div class="bsf-kv">${esc(item.label)}</div>
          </div>`).join("")}
      </div>
    </details>`);
}

function renderCaseSearch() {
  const target = region("case-search-results");
  const query = S.caseQuery.trim().toLowerCase();
  if (!query) { html(target, ""); return; }

  const snap = S.snapshot;
  const state = snap.workflow_state || {};
  const summary = state.attorney_summary || {};
  const hits = [];

  (summary.chronology || []).forEach((item) => {
    const text = `${item.date || ""} ${item.event || ""}`;
    if (text.toLowerCase().includes(query)) hits.push([t("hit_chronology"), text]);
  });
  (summary.available_evidence || []).forEach((item) => {
    const text = `${item.evidence || item.title || ""} ${item.relevance || ""}`;
    if (text.toLowerCase().includes(query)) hits.push([t("hit_evidence"), text]);
  });
  (snap.facts_register || []).forEach((row) => {
    if (String(row.fact_text).toLowerCase().includes(query)) hits.push([t("hit_fact"), row.fact_text]);
  });
  (snap.chat_messages || []).forEach((message) => {
    const text = plainMessageText(message.content);
    if (text.toLowerCase().includes(query)) hits.push([t("hit_discussion"), text.slice(0, 200)]);
  });

  if (!hits.length) {
    html(target, `<p class="bsf-caption">${esc(t("no_search_matches"))}</p>`);
    return;
  }
  const shown = hits.slice(0, 25);
  html(target, `
    ${shown.map(([kind, text]) => `
      <div class="bsf-item">${badge(kind, "neutral")}<div class="bsf-kv">${esc(text)}</div></div>`).join("")}
    ${hits.length > 25 ? `<p class="bsf-caption">${esc(t("showing_matches", { total: hits.length }))}</p>` : ""}`);
}

function plainMessageText(content) {
  const text = String(content || "");
  if (text.trim().startsWith("{")) {
    try {
      const parsed = JSON.parse(text);
      return isRTL() ? (parsed.answer_ar || parsed.answer_en || "") : (parsed.answer_en || parsed.answer_ar || "");
    } catch (error) { /* fall through to the raw text */ }
  }
  // Legacy replies are stored as HTML; search their words, not their tags.
  return text.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
}
/* ============================================================
   Upload queues

   Files accumulate across separate picks, exactly as the Streamlit
   uploader did, and each one can be removed before processing.
   ============================================================ */
const UPLOAD_REGIONS = { documents: "upload-file-list", agreement: "agreement-file-list" };

function fileKey(file) {
  return `${file.name}:${file.size}:${file.lastModified}`;
}

function addUploadFiles(kind, fileList) {
  const queue = S.uploads[kind];
  const seen = new Set(queue.map(fileKey));
  Array.from(fileList || []).forEach((file) => {
    if (!seen.has(fileKey(file))) {
      seen.add(fileKey(file));
      queue.push(file);
    }
  });
  renderUploadQueue(kind);
}

function removeUploadFile(kind, index) {
  S.uploads[kind].splice(index, 1);
  renderUploadQueue(kind);
}

function clearUploadQueue(kind) {
  S.uploads[kind] = [];
  renderUploadQueue(kind);
}

function renderUploadQueue(kind) {
  const target = region(UPLOAD_REGIONS[kind]);
  if (!target) return;
  const queue = S.uploads[kind];
  if (!queue.length) { html(target, ""); return; }
  html(target, `
    <p class="bsf-caption">${esc(t("files_queued", { count: queue.length }))}</p>
    ${queue.map((file, index) => `
      <div class="bsf-fileitem">
        <span class="bsf-filename">${esc(file.name)}</span>
        <button type="button" class="bsf-iconbtn" data-action="remove-upload"
                data-kind="${esc(kind)}" data-index="${index}"
                aria-label="${esc(t("remove_file"))}">&times;</button>
      </div>`).join("")}`);
}

/* ============================================================
   Documents tab
   ============================================================ */
const FILE_PURPOSES = ["full_case", "evidence", "correspondence", "contract", "decision", "other"];

function renderDocumentsTab() {
  const select = region("file-purpose");
  if (select && !select.options.length) {
    select.innerHTML = FILE_PURPOSES.map((value) =>
      `<option value="${value}">${esc(t("purpose_" + value))}</option>`).join("");
  } else if (select) {
    Array.from(select.options).forEach((option) => {
      option.textContent = t("purpose_" + option.value);
    });
  }

  const counts = (S.snapshot && S.snapshot.counts) || {};
  const stored = region("documents-stored");
  if (counts.documents) {
    stored.textContent = t("documents_already_stored", { count: counts.documents });
    show(stored, true);
  } else {
    show(stored, false);
  }

  renderFactsRegister();
}

/* The unified case register (backend: case_register.py). One expander per
   category; every item links to the pages it was extracted from. */
function renderCaseRegister() {
  const target = region("case-register");
  if (!target) return;
  const reg = (S.snapshot && S.snapshot.case_register) || null;
  const counts = (reg && reg.counts) || {};
  const total = ["parties", "events", "facts", "issues"].reduce((sum, key) => sum + (counts[key] || 0), 0);
  if (!reg || !total) { html(target, `<p class="bsf-caption">${esc(t("register_empty"))}</p>`); return; }

  const merged = (item) => item.merged_count > 1
    ? ` ${badge(t("register_merged", { count: item.merged_count }), "neutral")}` : "";
  const sources = (item) => sourceLinks(item.source_page_ids || [], item.page_labels || []);
  const priority = (value) => badge(t(`priority_${value || "medium"}`),
    value === "high" || value === "critical" ? "flagged" : "neutral");
  const factStatus = (value) => badge(t(`fact_status_${value}`),
    value === "alleged" ? "review" : value === "stated" ? "verified" : "neutral");

  const sections = [
    ["parties", (p) => `
      <div class="bsf-item"><strong>${esc(p.name)}</strong>
        ${p.role ? badge(p.role, "ai") : ""} ${p.party_type ? `<span class="bsf-caption">${esc(p.party_type)}</span>` : ""}${merged(p)}
        ${sources(p)}</div>`],
    ["events", (e) => `
      <div class="bsf-item"><strong>${esc(e.date || "—")}</strong> ${e.event_type ? badge(e.event_type, "neutral") : ""}${merged(e)}
        <div>${esc(e.description)}</div>${sources(e)}</div>`],
    ["allegations", (f) => `
      <div class="bsf-item">${factStatus(f.status)} ${f.party ? `<strong>${esc(f.party)}:</strong>` : ""}
        ${esc(f.fact_text)}${merged(f)}${sources(f)}</div>`],
    ["issues", (i) => `
      <div class="bsf-item"><strong>${esc(i.issue_title)}</strong> ${priority(i.priority)}${merged(i)}
        ${i.issue_description ? `<div>${esc(i.issue_description)}</div>` : ""}
        ${(i.targeted_questions || []).length ? `<div class="bsf-caption">${esc(t("register_questions"))}: ${esc(i.targeted_questions.join(" · "))}</div>` : ""}
        ${sources(i)}</div>`],
    ["evidence_requests", (e) => `
      <div class="bsf-item"><strong>${esc(e.title)}</strong> ${priority(e.priority)}${merged(e)}
        ${e.description ? `<div>${esc(e.description)}</div>` : ""}
        ${e.purpose ? `<div class="bsf-caption">${esc(e.purpose)}</div>` : ""}</div>`],
    ["contradictions", (c) => `
      <div class="bsf-item">${esc(c.description)}
        ${c.clarification_required ? `<div class="bsf-caption">${esc(t("register_clarify", { text: c.clarification_required }))}</div>` : ""}
        ${sources(c)}</div>`],
  ];

  const metric = (key) => `
    <div class="bsf-metric">
      <span class="m-value">${esc(counts[key] || 0)}</span>
      <span class="m-label">${esc(t(`register_${key}`))}</span>
    </div>`;
  const src = reg.sources || {};

  html(target, `
    <div class="bsf-status-meta bsf-register-metrics">
      ${["parties", "events", "facts", "allegations", "issues", "evidence_requests", "contradictions"].map(metric).join("")}
    </div>
    <p class="bsf-caption">${esc(t("register_sources", { documents: src.documents || 0, usable: src.usable_pages || 0, pages: src.pages || 0 }))}</p>
    ${sections.map(([key, render]) => {
      const items = reg[key] || [];
      return `
        <details class="bsf-expander">
          <summary>${esc(t(`register_${key}`))} (${items.length})</summary>
          <div class="bsf-expander-body">
            ${items.length ? items.map(render).join("") : `<p class="bsf-caption">${esc(t("register_none"))}</p>`}
          </div>
        </details>`;
    }).join("")}`);
}

function renderFactsRegister() {
  const rows = (S.snapshot && S.snapshot.facts_register) || [];
  const target = region("facts-register");
  if (!rows.length) {
    html(target, `<p class="bsf-caption">${esc(t("no_facts_extracted"))}</p>`);
    return;
  }
  const needle = S.factsFilter.trim().toLowerCase();
  const filtered = needle
    ? rows.filter((row) => String(row.fact_text).toLowerCase().includes(needle))
    : rows;
  const shown = filtered.slice(0, 30);

  html(target, `
    ${shown.map((row) => `
      <div class="bsf-item">
        <div class="bsf-kv">${esc(row.fact_text)}</div>
        <div class="bsf-item-controls">
          ${provenanceBadge(row)}
          ${sourceLinks(row.page_ids, row.page_labels)}
          ${flagControls("fact", row.fact_id)}
        </div>
      </div>`).join("")}
    ${filtered.length > 30 ? `<p class="bsf-caption">${esc(t("showing_first_facts"))}</p>` : ""}`);
}

function provenanceBadge(row) {
  const source = row.source_type === "chat" ? t("badge_from_discussion") : t("badge_ai_extracted");
  const status = String(row.verification_status || "").toLowerCase();
  if (status === "verified") return badge(t("badge_attorney_verified"), "verified");
  if (status === "flagged") return badge(t("badge_attorney_flagged"), "flagged");

  const value = Number(row.confidence);
  if (!Number.isFinite(value)) return badge(t("badge_unverified", { source }), "review");
  const percent = `${Math.round(value * 100)}%`;
  if (value >= 0.8) return badge(t("badge_confidence_high", { source, value: percent }), "ai");
  if (value >= 0.5) return badge(t("badge_confidence_review", { source, value: percent }), "review");
  return badge(t("badge_confidence_low", { source, value: percent }), "review");
}

function sourceLinks(pageIds, labels) {
  if (!pageIds || !pageIds.length) return "";
  return `<span class="bsf-source-links">${pageIds.map((pageId, index) => `
    <button type="button" class="bsf-btn bsf-source-link" data-action="view-page" data-page-id="${esc(pageId)}">
      ${esc((labels && labels[index]) || t("source_page"))}
    </button>`).join("")}</span>`;
}

function flagControls(entityType, entityId) {
  if (!entityId) return "";
  return `
    <button type="button" class="bsf-btn" data-action="flag" data-flag="verified"
            data-entity-type="${esc(entityType)}" data-entity-id="${esc(entityId)}">${esc(t("verify"))}</button>
    <button type="button" class="bsf-btn" data-action="flag" data-flag="flagged"
            data-entity-type="${esc(entityType)}" data-entity-id="${esc(entityId)}">${esc(t("flag"))}</button>`;
}

/* ============================================================
   Accounting & forensic analysis tab

   Everything here is read from S.snapshot.accounting, which the /case
   endpoint rebuilds on every load (normalized ledger, open conflicts,
   cross-check summary, discrepancies, findings) — the same on-demand
   recomputation the Streamlit tab did on every rerun.
   ============================================================ */
function renderAccountingTab() {
  const snap = S.snapshot;
  if (!snap) return;

  const acc = snap.accounting || {};

  // Show the instructions the last analysis ran with, unless the user is
  // already typing new ones.
  const instructions = $("#accounting-instructions");
  if (instructions && !instructions.value && acc.instructions) instructions.value = acc.instructions;

  renderAccountingDocPicker(acc.documents || []);
  renderAccountingReport(acc.last_run_report || {});
  renderAccountingConflicts(acc.review_items || acc.pending_conflicts || []);
  renderAccountingLedger(acc.normalized_ledger || [], acc.has_line_items, acc.has_pending_review, acc.withheld_rows || 0);
  renderAccountingCrossCheck(acc.cross_check_summary || {});
  renderAccountingDiscrepancies(acc.discrepancies || []);
  renderAccountingFindings(acc.findings || {}, acc.run_metadata || {});
}

function renderAccountingReport(report) {
  const target = region("accounting-report");
  if (!target) return;
  if (!report || report.pages_in_scope === undefined) { html(target, ""); return; }
  const lines = [t("report_line", {
    financial: report.financial_pages || 0,
    scope: report.pages_in_scope || 0,
    rows: report.rows_added || 0,
    pending: report.pending_review_items || 0,
  })];
  const failures = (report.extraction_failures || 0) + (report.classification_failures || 0);
  const notes = [];
  if (failures) notes.push(alertBox(t("report_failures", { count: failures }), "warn"));
  if (report.rows_discarded) notes.push(`<p class="bsf-caption">${esc(t("report_discarded", { count: report.rows_discarded }))}</p>`);
  html(target, `<p class="bsf-caption">${esc(lines[0])}</p>${notes.join("")}`);
}

function renderAccountingDocPicker(documents) {
  const target = region("accounting-doc-picker");
  if (!target) return;

  // First time this case's documents are seen, default every one to
  // selected — the same "default = all" behaviour as the Streamlit
  // multiselect.
  if (!S.accountingSelectedDocs) {
    S.accountingSelectedDocs = new Set(documents.map((doc) => doc.case_document_id));
  }

  if (!documents.length) {
    html(target, `<p class="bsf-caption">${esc(t("no_documents_stored"))}</p>`);
    return;
  }

  html(target, `
    <div class="bsf-doc-picker">
      ${documents.map((doc) => `
        <label class="bsf-doc-picker-item">
          <input type="checkbox" data-action="toggle-accounting-doc" value="${esc(doc.case_document_id)}"
                 ${S.accountingSelectedDocs.has(doc.case_document_id) ? "checked" : ""}>
          <span>${esc(doc.original_filename || doc.case_document_id)}</span>
        </label>`).join("")}
    </div>`);
}

const REVIEW_FIELD_ORDER = [
  "date", "amount", "currency", "debit_or_credit", "description", "reference_number", "party_source", "running_balance",
];

/* Pending accounting review items. Each shows the transaction as currently
   understood, the system's interpretation and reasoning for every open
   field, the row as printed and the surrounding page text, and a place to
   give the correct answer. Nothing enters the ledger until answered. */
function renderAccountingConflicts(items) {
  const target = region("accounting-conflicts");
  if (!target) return;
  if (!items.length) {
    const acc = (S.snapshot && S.snapshot.accounting) || {};
    html(target, acc.has_line_items ? alertBox(t("all_reconciled"), "ok") : "");
    return;
  }

  const transactionMarkup = (transaction) => `
    <table class="bsf-table bsf-review-transaction">
      <tbody>
        ${REVIEW_FIELD_ORDER.filter((name) => transaction[name]).map((name) => {
          const cell = transaction[name];
          return `<tr class="${cell.pending ? "is-pending" : ""}">
            <th>${esc(t(`field_${name}`))}</th>
            <td>${esc(cell.value || "—")}${cell.pending ? ` ${badge(t("review_pending_marker"), "review")}` : ""}</td>
          </tr>`;
        }).join("")}
      </tbody>
    </table>`;

  const fieldMarkup = (item, field) => `
    <div class="bsf-conflict-field" data-row-id="${esc(item.row_id)}" data-field-name="${esc(field.field)}">
      <div class="bsf-conflict-field-name">
        ${esc(t(`field_${field.field}`))}
        ${badge(t(field.issue === "missing" ? "review_issue_missing" : "review_issue_uncertain"), field.issue === "missing" ? "flagged" : "review")}
      </div>
      <div class="bsf-kv"><strong>${esc(t("review_suggestion"))}:</strong>
        ${field.suggested_value ? esc(field.suggested_value) : `<em>${esc(t("review_no_suggestion"))}</em>`}</div>
      ${field.reason ? `<div class="bsf-kv"><strong>${esc(t("review_reasoning"))}:</strong> ${esc(field.reason)}</div>` : ""}
      <div class="bsf-conflict-custom">
        <input type="text" class="bsf-input" placeholder="${esc(t("review_answer_placeholder", { field: t(`field_${field.field}`) }))}">
        ${field.suggested_value ? `
          <button type="button" class="bsf-btn" data-action="accounting-confirm-field" data-use-suggestion="1"
                  data-value="${esc(field.suggested_value)}"
                  data-row-id="${esc(item.row_id)}" data-field-name="${esc(field.field)}">
            ${esc(t("review_use_suggestion"))}
          </button>` : ""}
        <button type="button" class="bsf-btn bsf-btn-primary" data-action="accounting-confirm-field"
                data-row-id="${esc(item.row_id)}" data-field-name="${esc(field.field)}">
          ${esc(t("review_save_answer"))}
        </button>
      </div>
    </div>`;

  html(target, `
    <h4 class="bsf-subsection">${esc(t("review_items_heading"))}</h4>
    ${alertBox(t("detail_review_items", { count: items.reduce((total, item) => total + (item.fields || []).length, 0) }), "warn")}
    ${items.map((item) => `
      <details class="bsf-expander bsf-review-item" open>
        <summary>${esc(t("review_item_title", { page: item.page_label || `${t("page_label")} ${item.page_number || "—"}` }))}</summary>
        <div class="bsf-expander-body">
          <div class="bsf-review-grid">
            <div>
              <div class="bsf-review-label">${esc(t("review_transaction"))}</div>
              ${transactionMarkup(item.transaction || {})}
              ${item.source_text ? `
                <div class="bsf-review-label">${esc(t("review_row_as_printed"))}</div>
                <pre class="bsf-source-text">${esc(item.source_text)}</pre>` : ""}
              ${item.page_excerpt ? `
                <div class="bsf-review-label">${esc(t("review_page_excerpt"))}</div>
                <pre class="bsf-source-text">${esc(item.page_excerpt)}</pre>` : ""}
            </div>
            <div>
              ${item.page_image_url ? `
                <button type="button" class="bsf-review-image" data-action="view-page" data-page-id="${esc(item.page_id)}">
                  <img src="${esc(backendUrl(item.page_image_url))}" alt="${esc(item.page_label || "")}" loading="lazy">
                </button>` : ""}
            </div>
          </div>
          ${(item.fields || []).map((field) => fieldMarkup(item, field)).join("")}
        </div>
      </details>`).join("")}`);
}

function renderAccountingLedger(ledger, hasLineItems, hasPendingReview, withheld) {
  const target = region("accounting-ledger");
  if (!target) return;

  // The ledger only ever holds reviewed rows, so it is safe to show while
  // other rows still wait for the user; those are counted, not shown.
  const withheldNote = withheld ? alertBox(t("ledger_withheld", { count: withheld }), "info") : "";

  if (!hasLineItems || !ledger.length) {
    html(target, withheldNote || `<p class="bsf-caption">${esc(t("no_line_items"))}</p>`);
    return;
  }

  html(target, `
    ${withheldNote}
    <table class="bsf-table">
      <thead>
        <tr>
          <th>${esc(t("column_page"))}</th>
          <th>${esc(t("column_fin_date"))}</th>
          <th>${esc(t("column_description"))}</th>
          <th>${esc(t("column_reference"))}</th>
          <th>${esc(t("column_debit_credit"))}</th>
          <th>${esc(t("column_amount"))}</th>
          <th>${esc(t("column_currency"))}</th>
          <th>${esc(t("column_row_status"))}</th>
        </tr>
      </thead>
      <tbody>
        ${ledger.map((item) => `
          <tr>
            <td>${esc(item.page_number)}</td>
            <td>${esc(item.date)}</td>
            <td>${esc(item.description)}</td>
            <td>${esc(item.reference_number || "")}</td>
            <td>${esc(item.debit_or_credit)}</td>
            <td>${esc(item.amount)}</td>
            <td>${esc(item.currency)}</td>
            <td>${item.row_status === "verified_with_corrections"
              ? badge((item.corrected_fields || []).map((name) => t(`field_${name}`)).join(", "), "provisional")
              : badge(item.row_status, "verified")}</td>
          </tr>
        `).join("")}
      </tbody>
    </table>
  `);
}
function renderAccountingCrossCheck(summary) {
  const target = region("accounting-crosscheck");
  if (!target) return;
  if (!summary || !Object.keys(summary).length) { html(target, ""); return; }
  const agree = !!summary.numbers_agree_overall;
  html(target, `
    <div class="bsf-metric-row">
      <div class="bsf-metric">
        <span class="m-value">${esc(summary.total_inflows || "—")}</span>
        <span class="m-label">${esc(t("metric_total_inflows"))}</span>
      </div>
      <div class="bsf-metric">
        <span class="m-value">${esc(summary.total_transfers_to_bank || "—")}</span>
        <span class="m-label">${esc(t("metric_bank_transfer_received"))}</span>
      </div>
      <div class="bsf-metric">
        <span class="m-value">${esc(summary.disputed_freeze_amount || "—")}</span>
        <span class="m-label">${esc(t("metric_disputed_freeze"))}</span>
      </div>
      <div class="bsf-metric">
        <span class="m-value">${agree ? badge(t("numbers_agree"), "verified") : badge(t("numbers_disagree"), "flagged")}</span>
        <span class="m-label">${esc(t("metric_numbers_agreement"))}</span>
      </div>
    </div>
    ${summary.primary_discrepancy_narrative ? alertBox(summary.primary_discrepancy_narrative, "info") : ""}`);
}

function renderAccountingDiscrepancies(discrepancies) {
  const target = region("accounting-discrepancies");
  if (!target) return;
  if (!discrepancies.length) { html(target, ""); return; }
  html(target, `
    <h4 class="bsf-subsection">${esc(t("discrepancies_heading"))}</h4>
    ${discrepancies.map((item) => `
      <div class="bsf-item">
        <div class="bsf-item-controls" style="justify-content:space-between; margin-top:0;">
          <strong>${esc(item.issue_title || "")}</strong>
          ${badge(item.category || "discrepancy", "review")}
        </div>
        <div class="bsf-kv">${esc(item.analysis || "")}</div>
        <div class="bsf-kv"><strong>${esc(t("evidence_reference"))}:</strong> <code>${esc(item.evidence_support || "—")}</code></div>
        ${item.source_quote ? `<p class="bsf-caption">"${esc(item.source_quote)}"</p>` : ""}
      </div>`).join("")}`);
}

const CLAIM_RESULT_BADGE_KIND = {
  SUPPORTED: "flagged",
  PARTIALLY_SUPPORTED: "review",
  CONTRADICTED: "verified",
  NOT_VERIFIABLE: "review",
  NO_FINANCIAL_EVIDENCE: "neutral",
  NOT_FINANCIAL_CLAIM: "neutral",
};

function renderAccountingFindings(findings, runMeta) {
  const target = region("accounting-findings");
  if (!target) return;
  const evaluations = (findings && findings.claim_evaluations) || [];
  if (!evaluations.length) { html(target, ""); return; }

  const meta = runMeta && runMeta.run_at ? `<p class="bsf-caption">${esc(t("findings_run_meta", {
    at: runMeta.run_at,
    claims: runMeta.claims_count || 0,
    source: t(`claims_source_${runMeta.claims_source || "attorney_review"}`),
    instructions: runMeta.instructions || t("no_instructions"),
  }))}</p>` : "";

  const resultBadge = (result) =>
    badge(t(`claim_result_${String(result || "").toLowerCase()}`), CLAIM_RESULT_BADGE_KIND[result] || "neutral");
  const counts = (findings && findings.result_counts) || {};
  const summary = `
    <div class="bsf-claim-summary">
      <span class="bsf-caption">${esc(t("claims_summary", { count: evaluations.length }))}</span>
      ${Object.keys(counts).map((result) => `${resultBadge(result)} <strong>${esc(counts[result])}</strong>`).join(" ")}
    </div>`;

  const rowsTable = (rows) => rows.length ? `
    <table class="bsf-table bsf-claim-rows">
      <thead><tr>
        <th>${esc(t("column_fin_date"))}</th><th>${esc(t("column_description"))}</th>
        <th>${esc(t("column_reference"))}</th><th>${esc(t("column_debit_credit"))}</th>
        <th>${esc(t("column_amount"))}</th><th>${esc(t("column_page"))}</th>
      </tr></thead>
      <tbody>${rows.map((row) => `<tr>
        <td>${esc(row.date || "")}</td><td>${esc(row.description || "")}</td>
        <td>${esc(row.reference_number || "")}</td><td>${esc(row.debit_or_credit || "")}</td>
        <td>${esc(row.amount || "")} ${esc(row.currency || "")}</td>
        <td>${row.page_id ? sourceLinks([row.page_id], [row.page_label || t("source_page")]) : ""}</td>
      </tr>`).join("")}</tbody>
    </table>` : "";

  const block = (label, body) => `
    <div class="bsf-claim-block">
      <div class="bsf-review-label">${esc(label)}</div>
      ${body}
    </div>`;

  html(target, `
    <h4 class="bsf-subsection">${esc(t("findings_heading"))}</h4>
    ${meta}
    ${summary}
    ${evaluations.map((item) => `
      <details class="bsf-expander bsf-claim" open>
        <summary>
          ${resultBadge(item.result)}
          <span class="bsf-claim-title">${esc(item.claim || "")}</span>
        </summary>
        <div class="bsf-expander-body">
          ${item.financial_question ? `<div class="bsf-kv"><strong>${esc(t("financial_question_label"))}:</strong> ${esc(item.financial_question)}</div>` : ""}
          ${block(t("expected_evidence_label"), `<div>${esc(item.expected_evidence || "—")}</div>`)}
          ${block(t("evidence_found_label"), (item.evidence_rows || []).length
            ? rowsTable(item.evidence_rows)
            : `<p class="bsf-caption">${esc(t("none_found"))}</p>`)}
          ${block(t("missing_evidence_label"), (item.missing_evidence || []).length
            ? `<ul class="bsf-claim-list">${item.missing_evidence.map((text) => `<li>${esc(text)}</li>`).join("")}</ul>`
            : `<p class="bsf-caption">${esc(t("none_identified"))}</p>`)}
          ${block(t("contradictions_label"), (item.contradictions || []).length
            ? item.contradictions.map((entry) => `
                <div class="bsf-claim-contradiction">
                  <div>${esc(entry.description || "")}</div>
                  ${rowsTable(entry.rows || [])}
                </div>`).join("")
            : `<p class="bsf-caption">${esc(t("none_identified"))}</p>`)}
          ${item.comparison ? block(t("comparison_label"), `<div>${esc(item.comparison)}</div>`) : ""}
          ${item.accounting_response ? `<div class="bsf-kv"><strong>${esc(t("accounting_response_label"))}:</strong> ${esc(item.accounting_response)}</div>` : ""}
          ${item.limitation ? `<p class="bsf-caption">${esc(item.limitation)}</p>` : ""}
          ${(item.unverified_record_ids || []).length ? alertBox(t("unverified_ids", { ids: item.unverified_record_ids.join(", ") }), "info") : ""}
          ${(item.no_longer_in_ledger || []).length ? alertBox(t("stale_ids", { ids: item.no_longer_in_ledger.join(", ") }), "warn") : ""}
        </div>
      </details>`).join("")}`);
}

/* ============================================================
   Attorney review tab
   ============================================================ */
function renderReviewTab() {
  const state = (S.snapshot && S.snapshot.workflow_state) || {};
  const summary = state.attorney_summary;
  const stateBox = region("review-state");

  if (!summary) {
    html(stateBox, alertBox(t("start_by_preparing_review"), "info"));
  } else if (state.summary_approved) {
    html(stateBox, alertBox(t("summary_approved_by_notice", { name: state.summary_approved_by || "—" }), "ok"));
  } else {
    html(stateBox, alertBox(t("review_and_correct_record"), "warn"));
  }

  const body = region("summary-body");
  if (!summary) {
    html(body, `<p class="bsf-caption">${esc(t("no_summary_generated"))}</p>`);
    return;
  }

  const support = (S.snapshot && S.snapshot.summary_support) || {};
  const ar = isRTL();
  const overview = ar ? summary.matter_overview_ar : summary.matter_overview_en;
  const missingOverview = ar ? t("no_arabic_summary") : t("no_english_summary");

  html(body, `
    <h4 class="bsf-subsection">${esc(t("essential_case_summary"))}</h4>
    ${overview
      ? `<div class="bilingual-panel ${ar ? "arabic-block" : "english-block"}">${renderMarkdown(overview)}</div>`
      : alertBox(missingOverview, "warn")}

    ${summaryQualityMarkup(summary)}
    ${exposureMarkup(summary)}
    ${partiesMarkup(support)}
    ${chronologyMarkup(support)}
    ${evidenceMarkup(support)}
    ${contradictionsMarkup(summary)}
    ${alertsMarkup(summary)}

    <hr class="bsf-divider">
    <form data-form="approve-summary">
      <label class="bsf-field">
        <span>${esc(t("reviewing_attorney_name"))}</span>
        <input type="text" class="bsf-input" name="reviewer" required
               value="${esc(state.summary_approved_by || "")}">
      </label>
      <label class="bsf-field">
        <span>${esc(t("approval_comments"))}</span>
        <textarea class="bsf-input" name="comments" rows="2"></textarea>
             </label>
       <div class="bsf-btn-row">
         <button type="submit" class="bsf-btn bsf-btn-primary">
           ${esc(t("approve_consolidated_review"))}
         </button>
       </div>
    </form>`);
}

function summaryQualityMarkup(summary) {
  const status = String(summary.summary_quality_status || "").toLowerCase();
  if (status === "complete" || status === "ok") return alertBox(t("narrative_checks_passed"), "ok");
  if (summary.summary_warning) return alertBox(summary.summary_warning, "warn");
  return status ? alertBox(t("narrative_checks_gaps"), "warn") : "";
}

const SEVERITY_ORDER = { critical: 0, high: 1, medium: 2, low: 3 };

function exposureMarkup(summary) {
  const ar = isRTL();
  const entries = [];

  (summary.bank_risks || []).forEach((item) => {
    const title = ar ? item.risk_ar : item.risk_en;
    if (!title) return;
    entries.push({
      kind: t("kind_bank_legal_risk"), title,
      why: (ar ? item.why_material_ar : item.why_material_en) || item.why_material || "",
      action: (ar ? item.recommended_response_ar : item.recommended_response_en) || "",
      severity: String(item.severity || "").toLowerCase(),
    });
  });
  (summary.bank_position_weaknesses || []).forEach((item) => {
    const title = ar ? item.weakness_ar : item.weakness_en;
    if (!title) return;
    entries.push({
      kind: t("kind_weakens_position"), title,
      why: (ar ? item.legal_significance_ar : item.legal_significance_en) || "",
      action: (ar ? item.recommended_response_ar : item.recommended_response_en) || "",
      severity: String(item.impact || "").toLowerCase(),
    });
  });
  (summary.bank_gaps || []).forEach((item) => {
    const title = ar ? item.gap_ar : item.gap_en;
    if (!title) return;
    entries.push({ kind: t("kind_decisive_gap"), title, why: "", action: "", severity: String(item.impact || "").toLowerCase() });
  });
  (summary.bank_legal_questions || []).forEach((item) => {
    const title = ar ? item.question_ar : item.question_en;
    if (!title) return;
    entries.push({ kind: t("kind_open_question"), title, why: "", action: "", severity: String(item.priority || "").toLowerCase() });
  });

  if (!entries.length) {
    return `<details class="bsf-expander"><summary>${esc(t("legal_exposure_and_position"))}</summary>
      <div class="bsf-expander-body"><p class="bsf-caption">${esc(t("no_exposure_points"))}</p></div></details>`;
  }

  entries.sort((a, b) => (SEVERITY_ORDER[a.severity] ?? 9) - (SEVERITY_ORDER[b.severity] ?? 9));

  return `
    <details class="bsf-expander" open>
      <summary>${esc(t("legal_exposure_and_position"))}</summary>
      <div class="bsf-expander-body">
        <p class="bsf-caption">${esc(t("exposure_sorted_caption"))}</p>
        ${entries.map((entry) => `
          <div class="bsf-issue">
            <div>${badge(entry.kind, "review")}
              ${entry.severity ? badge(severityLabel(entry.severity), severityKind(entry.severity)) : ""}</div>
            <h4>${esc(entry.title)}</h4>
            ${entry.why ? `<div class="bsf-kv">${esc(entry.why)}</div>` : ""}
            ${entry.action ? alertBox(t("recommended_action") + entry.action, "info") : ""}
          </div>`).join("")}
      </div>
    </details>`;
}

function severityLabel(value) {
  const key = String(value || "").toLowerCase();
  return SEVERITY_ORDER[key] !== undefined ? t("severity_" + key) : value;
}

function severityKind(value) {
  const key = String(value || "").toLowerCase();
  if (key === "critical" || key === "high") return "flagged";
  if (key === "medium") return "review";
  return "neutral";
}

function partiesMarkup(support) {
  const parties = support.ordered_parties || [];
  return `
    <details class="bsf-expander">
      <summary>${esc(t("main_parties"))}</summary>
      <div class="bsf-expander-body">
        ${parties.length ? `
          <table class="bsf-table">
            <thead><tr><th>${esc(t("column_name"))}</th><th>${esc(t("column_role"))}</th></tr></thead>
            <tbody>${parties.map((item) => `
              <tr><td>${esc(item.name || "")}</td><td>${esc(item.role || "")}</td></tr>`).join("")}</tbody>
          </table>` : `<p class="bsf-caption">${esc(t("no_parties_confirmed"))}</p>`}
      </div>
    </details>`;
}

function chronologyMarkup(support) {
  const rows = support.ordered_chronology || [];
  return `
    <details class="bsf-expander">
      <summary>${esc(t("chronology_and_pages"))}</summary>
      <div class="bsf-expander-body">
        ${rows.length ? `
          <table class="bsf-table">
            <thead><tr>
              <th>${esc(t("column_date"))}</th><th>${esc(t("column_event"))}</th>
              <th>${esc(t("column_status"))}</th><th>${esc(t("column_chronology_basis"))}</th>
              <th>${esc(t("column_related_evidence_pages"))}</th>
            </tr></thead>
            <tbody>${rows.map(({ item, page_labels }) => `
              <tr>
                <td>${esc(item.date || "")}</td>
                <td>${esc(item.event || "")}</td>
                <td>${esc(item.status || "uncertain")}</td>
                <td>${esc(chronologyBasis(item))}</td>
                <td>${sourceLinks(item.source_page_ids || [], page_labels)}</td>
              </tr>`).join("")}</tbody>
          </table>` : `<p class="bsf-caption">${esc(t("no_dated_events"))}</p>`}
      </div>
    </details>`;
}

function chronologyBasis(item) {
  if (!item.date) {
    return item.chronology_basis === "inferred_sequence" ? t("basis_inferred") : t("basis_source_no_date");
  }
  return t("basis_dated_source");
}

function evidenceMarkup(support) {
  const rows = support.ordered_evidence || [];
  return `
    <details class="bsf-expander">
      <summary>${esc(t("available_evidence"))}</summary>
      <div class="bsf-expander-body">
        ${rows.length ? `
          <table class="bsf-table">
            <thead><tr>
              <th>${esc(t("column_evidence"))}</th><th>${esc(t("column_relevance"))}</th>
              <th>${esc(t("column_limitations"))}</th><th>${esc(t("column_original_pages"))}</th>
            </tr></thead>
            <tbody>${rows.map(({ item, page_ids, page_labels }) => `
              <tr>
                <td>${esc(item.evidence || item.title || "")}</td>
                <td>${esc(item.relevance || "")}</td>
                <td>${esc(item.limitations || item.limitation || "")}</td>
                <td>${sourceLinks(page_ids, page_labels)}</td>
              </tr>`).join("")}</tbody>
          </table>` : `<p class="bsf-caption">${esc(t("no_evidence_recorded"))}</p>`}
      </div>
    </details>`;
}

function contradictionsMarkup(summary) {
  const ar = isRTL();
  const rows = summary.legal_contradictions || [];
  return `
    <details class="bsf-expander">
      <summary>${esc(t("material_contradictions"))}</summary>
      <div class="bsf-expander-body">
        ${rows.length ? rows.slice(0, 10).map((item, index) => {
          const issue = ar ? item.issue_ar : item.issue_en;
          const relevance = ar ? item.legal_relevance_ar : item.legal_relevance_en;
          if (!issue) return "";
          return `<div class="bsf-issue">
            <h4>${index + 1}. ${esc(issue)}</h4>
            ${relevance ? `<div class="bsf-kv">${esc(relevance)}</div>` : ""}
            <p class="bsf-caption">${esc(t("impact_level"))}${esc(severityLabel(item.impact))}</p>
          </div>`;
        }).join("") : `<p class="bsf-caption">${esc(t("no_material_contradiction"))}</p>`}
        <p class="bsf-caption">${esc(t("contradiction_caption"))}</p>
      </div>
    </details>`;
}

function alertsMarkup(summary) {
  const ar = isRTL();
  const rows = summary.source_verification_alerts || [];
  return `
    <details class="bsf-expander">
      <summary>${esc(t("source_verification_alerts"))}</summary>
      <div class="bsf-expander-body">
        ${rows.length ? rows.slice(0, 12).map((item, index) => {
          const alert = ar ? item.alert_ar : item.alert_en;
          const reason = ar ? item.reason_ar : item.reason_en;
          if (!alert) return "";
          return `<div class="bsf-item"><strong>${index + 1}. ${esc(alert)}</strong>
            ${reason ? `<div class="bsf-kv">${esc(reason)}</div>` : ""}</div>`;
        }).join("") : `<p class="bsf-caption">${esc(t("no_verification_alerts"))}</p>`}
      </div>
    </details>`;
}

/* ============================================================
   Legal analysis tab
   ============================================================ */
function renderAnalysisTab() {
  const state = (S.snapshot && S.snapshot.workflow_state) || {};
  const analysis = state.analysis;
  const body = region("analysis-body");

  if (!analysis) {
    html(body, `<p class="bsf-caption">${esc(t("run_analysis_hint"))}</p>`);
  } else {
    html(body, `
      <div class="bsf-metric-row">
        <div class="bsf-metric">
          <span class="m-value">${esc(analysis.overall_posture || "unresolved")}</span>
          <span class="m-label">${esc(t("metric_overall_posture"))}</span>
        </div>
        <div class="bsf-metric">
          <span class="m-value">${esc(analysis.knowledge_base_authority_count || 0)}</span>
          <span class="m-label">${esc(t("metric_kb_authorities"))}</span>
        </div>
      </div>
      <p class="bsf-caption">${esc(t("source_policy_kb_only"))}</p>
      <div>${renderMarkdown(analysis.executive_summary || "")}</div>
      ${(analysis.issues || []).map((item) => `
        <div class="bsf-issue">
          <h4>${esc(item.issue_title || "")}</h4>
          ${(item.applicable_rules || []).length
            ? `<div class="bsf-kv"><strong>${esc(t("kb_rules"))}</strong></div>
               <ul>${item.applicable_rules.map((rule) => `
                 <li>${esc(rule.proposition || "")} <code>[${esc((rule.node_ids || []).join(", "))}]</code></li>`).join("")}</ul>`
            : alertBox(t("no_citable_rule"), "warn")}
          <div class="bsf-kv"><strong>${esc(t("our_position"))}</strong> ${esc(item.our_position || "")}</div>
          <div class="bsf-kv"><strong>${esc(t("opponent_position"))}</strong> ${esc(item.opponent_position || "")}</div>
          <div class="bsf-kv"><strong>${esc(t("response_label"))}</strong> ${esc(item.response || "")}</div>
          <div class="bsf-kv"><strong>${esc(t("conclusion_label"))}</strong> ${conclusionBadge(item.conclusion)}</div>
          <div class="bsf-kv"><strong>${esc(t("residual_risk_label"))}</strong> ${esc(item.residual_risk || "")}</div>
        </div>`).join("")}

      <div class="bsf-btn-row">
        <button type="button" class="bsf-btn" data-action="defence-plan"
                ${state.summary_approved ? "" : "disabled"}>${esc(t("develop_defence_plan"))}</button>
      </div>
      ${state.summary_approved ? "" : `<p class="bsf-caption">${esc(t("defence_plan_locked"))}</p>`}`);
  }

  const strategy = state.strategy;
  const strategyBody = region("strategy-body");
  if (!strategy) { html(strategyBody, ""); return; }
  html(strategyBody, `
    <h3 class="bsf-section-title">${esc(t("defence_structure"))}</h3>
    <div>${renderMarkdown((strategy.primary_theory || {}).description || "")}</div>
    <ul>${(strategy.actions || []).map((action) => `
      <li><strong>${esc(action.action_type || t("action_fallback"))}</strong> — ${esc(action.description || "")}
        (${esc(t("priority_label", { value: action.priority || "medium" }))})</li>`).join("")}</ul>`);
}

function conclusionBadge(value) {
  const text = String(value || "unresolved");
  const lower = text.toLowerCase();
  const kind = lower === "supported" ? "verified" : (lower === "unresolved" ? "review" : "neutral");
  return badge(text, kind);
}
/* ============================================================
   Written pleading tab
   ============================================================ */
function renderPleadingTab() {
  const state = (S.snapshot && S.snapshot.workflow_state) || {};
  const versions = state.pleading_versions || [];
  const memo = state.memo;

  const stateBox = region("pleading-state");
  if (!memo && state.summary_approved) html(stateBox, alertBox(t("pleading_intro"), "info"));
  else if (memo) html(stateBox, alertBox(
    t("current_pleading_status", { version: versions.length, status: state.pleading_status }), "ok"));
  else html(stateBox, "");

const legalAnalysisReady = Boolean(state.analysis);

const accountingStatus = String(
  state.accounting_status || ""
).toLowerCase();

const accountingReady = [
  "forensic_complete",
  "complete_no_transactions",
].includes(accountingStatus);

const canDraft =
  state.summary_approved &&
  state.attorney_summary &&
  legalAnalysisReady &&
  accountingReady &&
  !state.case_dirty;

const generate = document.querySelector(
  '[data-action="generate-pleading"]'
);

if (generate) {
  generate.disabled = !canDraft;
}

const locked = region("pleading-locked");

if (canDraft) {

  html(locked, "");

} else {

  let reason = t("block_not_approved");

  if (state.case_dirty) {
    reason = t("block_case_dirty");

  } else if (!state.attorney_summary) {
    reason = t("block_no_summary");

  } else if (!state.summary_approved) {
    reason = t("block_not_approved");

  } else if (!legalAnalysisReady) {
    reason = t("block_no_legal_analysis");

  } else if (!accountingReady) {
    reason = t("block_accounting_incomplete");
  }

  html(
    locked,
    `<p class="bsf-caption">${esc(
      t("locked_reason", { reason })
    )}</p>`
  );
}

  const body = region("pleading-body");
  if (!memo) { html(body, ""); return; }

  const lang = S.lang;
  const downloadKey = lang === "ar" ? "download_arabic_pleading" : "download_english_pleading";

  html(body, `
    <div class="bsf-pleading-body ${lang === "ar" ? "arabic-block" : "english-block"}"
         data-region="pleading-markdown">${esc(t("loading"))}</div>

    <div class="bsf-btn-row">
      <button type="button" class="bsf-btn" data-action="download" data-fmt="md" data-lang="${lang}">
        ${esc(t(downloadKey))}</button>
      <button type="button" class="bsf-btn" data-action="download" data-fmt="docx" data-lang="${lang}">
        ${esc(t("download_combined_pleading"))}</button>
    </div>

    <details class="bsf-expander">
      <summary>${esc(t("attorney_checks"))}</summary>
      <div class="bsf-expander-body">
        <ul>${(memo.attorney_checks || []).map((item) => `<li>${esc(item)}</li>`).join("")}</ul>
        <p class="bsf-caption">${esc(t("source_ids_used"))} ${esc((memo.source_ids_used || []).join(", "))}</p>
      </div>
    </details>

    <hr class="bsf-divider">
    <h3 class="bsf-section-title">${esc(t("iterative_attorney_review"))}</h3>
    <p class="bsf-caption">${esc(t("iterative_caption"))}</p>

    <form data-form="revise-pleading">
      <label class="bsf-field">
        <span>${esc(t("requested_amendment"))}</span>
        <textarea class="bsf-input" name="revision_request" rows="3"
                  placeholder="${esc(t("amendment_placeholder"))}" required></textarea>
      </label>
      <div class="bsf-btn-row">
        <button type="submit" class="bsf-btn bsf-btn-primary"
                ${state.pleading_status === "final" ? "disabled" : ""}>${esc(t("create_revised_version"))}</button>
        <button type="button" class="bsf-btn" data-action="reopen-pleading"
                ${state.pleading_status === "final" ? "" : "disabled"}>${esc(t("reopen_final_pleading"))}</button>
      </div>
    </form>
    <div data-region="revise-job"></div>

    ${versionHistoryMarkup(versions)}

    <hr class="bsf-divider">
    ${state.pleading_status === "final"
      ? alertBox(t("pleading_final_notice", { name: state.pleading_finalised_by || "—" }), "ok")
      : alertBox(t("pleading_draft_notice", { number: versions.length }), "info")}
    <form data-form="finalise-pleading">
      <label class="bsf-field">
        <span>${esc(t("final_approving_attorney"))}</span>
        <input type="text" class="bsf-input" name="final_reviewer" required
               value="${esc(state.pleading_finalised_by || "")}">
      </label>
      <button type="submit" class="bsf-btn bsf-btn-primary"
              ${state.pleading_status === "final" ? "disabled" : ""}>${esc(t("mark_final"))}</button>
    </form>`);

  loadPleadingMarkdown(lang);
}

async function loadPleadingMarkdown(lang) {
  const target = region("pleading-markdown");
  if (!target) return;
  try {
    // Rendered from the backend's own memo_to_markdown so the document on
    // screen matches the exported .md and .docx exactly.
    const markdown = await apiText("/pleading/export", { case_id: S.caseId, fmt: "md", lang });
    html(target, renderMarkdown(markdown));
  } catch (error) {
    html(target, alertBox(t("request_failed", { error: error.message }), "flag"));
  }
}

function versionHistoryMarkup(versions) {
  if (versions.length < 2) return "";
  const selected = S.compareVersion || versions[0].version;
  const current = versions[versions.length - 1];
  const chosen = versions.find((item) => item.version === selected) || versions[0];

  return `
    <div class="bsf-version-history">
      <h4 class="bsf-subsection">${esc(t("version_history"))}</h4>
      <div class="bsf-version-row">
        <select class="bsf-input bsf-field-grow" data-action="select-version">
          ${versions.map((item) => `
            <option value="${item.version}" ${item.version === selected ? "selected" : ""}>
              ${esc(t("version_label", { number: item.version }))}</option>`).join("")}
        </select>
        <button type="button" class="bsf-btn" data-action="restore-version" data-version="${selected}"
                ${selected === current.version ? "disabled" : ""}>${esc(t("restore_this_version"))}</button>
      </div>
      <p class="bsf-caption">${esc(t("change_instruction"))}${esc(chosen.note || "")}</p>
      ${selected !== current.version ? `
        <details class="bsf-expander">
          <summary>${esc(t("compare_with_current"))}</summary>
          <div class="bsf-expander-body">
            <p class="bsf-caption">${esc(t("redline_caption", { old: selected, new: current.version }))}</p>
            <div class="bsf-diff ${isRTL() ? "arabic-block" : "english-block"}">
              ${renderDiff(memoPlainText(chosen.draft, S.lang), memoPlainText(current.draft, S.lang))}
            </div>
          </div>
        </details>` : ""}
    </div>`;
}

/* ============================================================
   Case discussion tab
   ============================================================ */
function renderDiscussionTab() {
  const submit = region("ask-submit");
  if (submit) submit.textContent = t("send");

  const messages = (S.snapshot && S.snapshot.chat_messages) || [];
  html(region("chat"), messages.map(messageMarkup).join(""));
  const chat = region("chat");
  if (chat) chat.scrollTop = chat.scrollHeight;
}

/* Assistant replies exist in the case record in two formats. The WebApp
   stores a JSON payload; the earlier Streamlit build stored the already
   rendered HTML ("<div class=\"arabic-block bilingual-panel\" …>"). Any
   case with chat history from before the migration holds the second kind,
   which is why only some conversations showed raw markup. */
const STORED_HTML_RE = /^\s*<(div|p|span|h[1-6]|ul|ol|pre|blockquote|table)[\s>]/i;

function looksLikeStoredHtml(text) {
  return STORED_HTML_RE.test(text) || /class="(arabic|english)-block/.test(text);
}

/* The markup came from our own backend, but it is still persisted data, so
   active content is stripped before it is inserted. */
function sanitiseStoredHtml(markup) {
  return String(markup)
    .replace(/<\s*(script|style|iframe|object|embed|link)\b[\s\S]*?<\s*\/\s*\1\s*>/gi, "")
    .replace(/<\s*(script|style|iframe|object|embed|link)\b[^>]*>/gi, "")
    .replace(/\son\w+\s*=\s*("[^"]*"|'[^']*'|[^\s>]+)/gi, "")
    .replace(/javascript:/gi, "");
}

function messageMarkup(message) {
  const role = message.role === "user" ? "user" : "assistant";
  const text = String(message.content || "");
  let inner;

  if (role === "assistant" && text.trim().startsWith("{")) {
    try {
      const parsed = JSON.parse(text);
      inner = answerMarkup(parsed);
    } catch (error) {
      inner = renderMarkdown(text);
    }
  } else if (role === "assistant" && looksLikeStoredHtml(text)) {
    inner = sanitiseStoredHtml(text);
  } else {
    inner = renderMarkdown(text);
  }
  return `<div class="bsf-msg bsf-msg-${role}">${inner}</div>`;
}

function answerMarkup(answer) {
  const ar = isRTL();
  let body = (ar ? answer.answer_ar : answer.answer_en) || answer.answer_en || answer.answer_ar || "";
  const uncertainties = answer.uncertainties || [];
  const sources = answer.source_ids || [];

  if (uncertainties.length) {
    body += `\n\n## ${t("uncertainties_heading")}\n` + uncertainties.map((item) => `- ${item}`).join("\n");
  }
  if (sources.length) {
    body += `\n\n**${t("source_ids_label")}** ` + sources.join(", ");
  }
  return `<div class="${ar ? "arabic-block" : "english-block"}">${renderMarkdown(body)}</div>`;
}

/* ============================================================
   Agreement review workflow
   ============================================================ */
const AGREEMENT_STEP_KEYS = [
  "step_upload_agreement", "step_confirm_classification", "step_map_clauses", "step_review_and_amend",
];

function agreementLabel(value) {
  const key = String(value || "");
  const map = {
    nda: "agreement_nda", banking_agreement: "agreement_banking", vendor_agreement: "agreement_vendor",
    customer_agreement: "agreement_customer", employment_agreement: "agreement_employment",
    consultancy_agreement: "agreement_consultancy", outsourcing_agreement: "agreement_outsourcing",
    data_processing_agreement: "agreement_data_processing",
    software_licence_agreement: "agreement_software_licence",
    procurement_agreement: "agreement_procurement", partnership_agreement: "agreement_partnership",
    other_agreement: "agreement_other",
    bank_financial_institution: "relationship_bank_financial_institution",
    bank_vendor: "relationship_bank_vendor", bank_customer: "relationship_bank_customer",
    financial_institution_technology_provider: "relationship_financial_institution_technology_provider",
    institution_service_provider: "relationship_institution_service_provider",
    employer_employee: "relationship_employer_employee", company_consultant: "relationship_company_consultant",
    supplier_customer: "relationship_supplier_customer",
    institution_institution: "relationship_institution_institution",
    other_relationship: "relationship_other",
  };
  return map[key] ? t(map[key]) : key;
}

function renderAgreement() {
  const snap = S.snapshot;
  if (!snap) return;
  region("agreement-title").textContent = snap.display_name || t("default_agreement_name");
  region("agreement-ref").textContent = snap.reference;

  const state = snap.agreement_state || {};
  const complete = [
    (snap.counts || {}).documents > 0,
    Boolean(state.profile),
    Boolean(state.clause_map),
    Boolean(state.review),
  ];
  const firstOpen = complete.findIndex((done) => !done);
  html(region("agreement-stepper"), AGREEMENT_STEP_KEYS.map((key, index) => {
    const status = complete[index] ? "complete" : (index === firstOpen ? "current" : "upcoming");
    const symbol = complete[index] ? "\u2713" : (index === firstOpen ? String(index + 1) : "\u25CB");
    return `<div class="step-card ${status}">
      <div class="step-icon">${symbol}</div>
      <div class="step-label">${esc(t(key))}</div>
    </div>`;
  }).join(""));

  renderClassificationTab(state);
  renderClauseTab(state);
  renderAgreementReviewTab(state);
  renderAgreementDiscussionTab(state);
}

function renderClassificationTab(state) {
  const typeSelect = region("agreement-types");
  const relSelect = region("relationship-types");
  const profile = state.profile || {};
  const detected = state.classification || {};

  const fill = (select, values, chosen) => {
    select.innerHTML = values.map((value) =>
      `<option value="${esc(value)}" ${value === chosen ? "selected" : ""}>${esc(agreementLabel(value))}</option>`).join("");
  };
  fill(typeSelect, S.bootstrap.agreement_types || [],
    profile.agreement_type || detected.agreement_type);
  fill(relSelect, S.bootstrap.relationship_types || [],
    profile.relationship_type || detected.relationship_type);

  const form = document.querySelector('[data-form="confirm-classification"]');
  const field = (name) => form.querySelector(`[name="${name}"]`);
  field("represented_party").value = profile.represented_party || "";
  field("counterparty").value = profile.counterparty || "";
  field("review_objective").value = profile.review_objective || "";

  const box = region("classification-detected");
  if (!detected.agreement_type) { html(box, ""); return; }
  const confidence = Number(detected.confidence);
  html(box, `
    ${alertBox(t("detected_with_confidence", {
      value: Number.isFinite(confidence) ? `${Math.round(confidence * 100)}%` : "—",
    }), "info")}
    <div class="bsf-kv"><strong>${esc(t("detection_reasons"))}</strong>
      ${esc((detected.reasons || []).join("; "))}</div>`);
}

function renderClauseTab(state) {
  const locked = region("clauses-locked");
  const extract = document.querySelector('[data-action="extract-clauses"]');
  if (!state.profile) {
    html(locked, alertBox(t("confirm_classification_first"), "warn"));
    if (extract) extract.disabled = true;
  } else {
    html(locked, "");
    if (extract) extract.disabled = false;
  }

  const map = state.clause_map || {};
  const clauses = map.clauses || [];
  const alerts = region("clause-alerts");

  if (!clauses.length) {
    html(alerts, "");
    html(region("clause-list"), `<p class="bsf-caption">${esc(t("no_clauses"))}</p>`);
    return;
  }

  const missingSections = map.missing_or_unclear_sections || [];
  const missingDeps = map.missing_dependencies || [];
  const conflicts = map.cross_document_conflicts || [];
  const metadata = map.processing_metadata || {};

  html(alerts, `
    <div class="bsf-metric-row">
      ${[["metric_missing_sections", missingSections.length],
         ["metric_missing_dependencies", missingDeps.length],
         ["metric_cross_document_conflicts", conflicts.length]].map(([key, value]) => `
        <div class="bsf-metric"><span class="m-value">${value}</span>
          <span class="m-label">${esc(t(key))}</span></div>`).join("")}
    </div>
    ${listExpander("missing_sections_expander", missingSections)}
    ${listExpander("missing_dependencies_expander", missingDeps, t("provisional_dependency_caption"))}
    ${listExpander("cross_document_conflicts_expander", conflicts)}
    <p class="bsf-caption">${esc(t("clause_map_metadata", {
      pages: metadata.page_structure_count || 0, chunks: metadata.chunk_count || 0,
    }))}</p>`);

  const needle = S.clauseFilter.trim().toLowerCase();
  const filtered = needle
    ? clauses.filter((clause) => `${clause.heading || ""} ${clause.clause_number || ""} ${clause.full_text || ""}`
        .toLowerCase().includes(needle))
    : clauses;

  html(region("clause-list"), filtered.map((clause) => `
    <div class="bsf-issue">
      <h4>${esc(clause.clause_number ? `${clause.clause_number}. ` : "")}${esc(clause.heading || t("clause"))}</h4>
      ${clause.completeness_status ? badge(clause.completeness_status, "neutral") : ""}
      <details class="bsf-expander">
        <summary>${esc(t("full_clause_text"))}</summary>
        <div class="bsf-expander-body">${renderMarkdown(clause.full_text || t("no_clause_text"))}</div>
      </details>
      ${(clause.exceptions_or_carve_outs || []).length
        ? `<p class="bsf-caption">${esc(t("exceptions_carve_outs"))} ${esc(clause.exceptions_or_carve_outs.join("; "))}</p>` : ""}
      ${(clause.related_clause_ids || []).length
        ? `<p class="bsf-caption">${esc(t("related_clauses"))} ${esc(clause.related_clause_ids.join(", "))}</p>` : ""}
    </div>`).join(""));
}

function listExpander(titleKey, items, caption) {
  if (!items.length) return "";
  return `
    <details class="bsf-expander">
      <summary>${esc(t(titleKey, { count: items.length }))}</summary>
      <div class="bsf-expander-body">
        ${caption ? `<p class="bsf-caption">${esc(caption)}</p>` : ""}
        <ul>${items.map((item) => `<li>${esc(typeof item === "string" ? item : JSON.stringify(item))}</li>`).join("")}</ul>
      </div>
    </details>`;
}

function renderAgreementReviewTab(state) {
  const locked = region("review-locked");
  const run = document.querySelector('[data-action="run-agreement-review"]');
  if (!state.clause_map) {
    html(locked, alertBox(t("extract_clause_map_first"), "warn"));
    if (run) run.disabled = true;
  } else {
    html(locked, "");
    if (run) run.disabled = false;
  }

  const review = state.review;
  const body = region("agreement-review-body");
  if (!review) { html(body, ""); return; }

  const ar = isRTL();
  const critical = review.critical_points || [];
  const missing = review.missing_protections || [];
  const conflicts = review.cross_clause_conflicts || [];
  const provisional = review.provisional_items || [];
  const negotiation = review.negotiation_position || {};

  html(body, `
    <div class="bilingual-panel ${ar ? "arabic-block" : "english-block"}">
      ${renderMarkdown((ar ? review.executive_summary_ar : review.executive_summary_en) || "")}
    </div>

    <div class="bsf-metric-row">
      ${[["metric_critical_points", critical.length],
         ["metric_missing_protections", missing.length],
         ["metric_cross_clause_conflicts", conflicts.length]].map(([key, value]) => `
        <div class="bsf-metric"><span class="m-value">${value}</span>
          <span class="m-label">${esc(t(key))}</span></div>`).join("")}
    </div>
    ${provisional.length ? `<p class="bsf-caption">${esc(t("provisional_findings_note", { count: provisional.length }))}</p>` : ""}
    ${listExpander("critical_points_expander", critical)}
    ${listExpander("missing_protections_expander", missing)}
    ${listExpander("cross_clause_conflicts_expander", conflicts)}

    <h4 class="bsf-subsection">${esc(t("clause_by_clause_review"))}</h4>
    ${(review.clause_reviews || []).map(clauseReviewMarkup).join("")}

    <h4 class="bsf-subsection">${esc(t("negotiation_prep"))}</h4>
    ${negotiationMarkup(negotiation)}`);
}

function clauseReviewMarkup(item) {
  const ar = isRTL();
  const commercial = ar ? item.commercial_finding_ar : item.commercial_finding_en;
  const legal = ar ? item.legal_finding_ar : item.legal_finding_en;
  const change = ar ? item.recommended_change_ar : item.recommended_change_en;
  const wording = ar ? item.proposed_wording_ar : item.proposed_wording_en;
  const question = ar ? item.client_question_ar : item.client_question_en;

  return `
    <div class="bsf-issue">
      <h4>${esc(item.clause_id || "")}</h4>
      <div>
        ${item.risk_level ? badge(severityLabel(item.risk_level), severityKind(item.risk_level)) : ""}
        ${item.review_status === "final" ? badge(t("badge_final"), "final") : ""}
        ${item.review_status === "provisional" ? badge(t("badge_provisional"), "provisional") : ""}
      </div>
      ${commercial ? `<div class="bsf-kv">${esc(commercial)}</div>` : ""}
      ${legal ? `<div class="bsf-kv">${esc(legal)}</div>` : ""}
      ${(item.weaknesses || []).length
        ? `<p class="bsf-caption">${esc(t("weaknesses_identified"))} ${esc(item.weaknesses.join("; "))}</p>` : ""}
      ${(item.missing_dependencies || []).length
        ? alertBox(t("missing_dependencies_provisional") + " " + item.missing_dependencies.join("; "), "warn") : ""}
      ${(item.affected_related_clause_ids || []).length
        ? `<p class="bsf-caption">${esc(t("also_affects_clauses"))} ${esc(item.affected_related_clause_ids.join(", "))}</p>` : ""}
      ${change ? `<div class="bsf-kv"><strong>${esc(t("recommended_action"))}</strong> ${esc(change)}</div>` : ""}
      ${wording ? `<div class="bilingual-panel ${ar ? "arabic-block" : "english-block"}">${esc(wording)}</div>` : ""}
      ${question ? alertBox(t("question_for_client", { question }), "info") : ""}
      <p class="bsf-caption">${esc(t("kb_authority_ids"))}
        ${esc((item.authority_node_ids || []).join(", ") || t("none_retrieved"))}</p>
      <div class="bsf-item-controls">
        <label class="bsf-checkbox">
          <span>${esc(t("attorney_decision"))}</span>
          <select class="bsf-input" data-action="clause-decision" data-clause-id="${esc(item.clause_id || "")}">
            ${["pending", "accept", "modify", "reject", "needs_instruction"].map((value) =>
              `<option value="${value}">${esc(t("decision_" + value))}</option>`).join("")}
          </select>
        </label>
        ${flagControls("agreement_clause", item.clause_id)}
      </div>
    </div>`;
}

function negotiationMarkup(negotiation) {
  const groups = [
    ["non_negotiable", "position_non_negotiable", "flagged"],
    ["high_priority", "position_high_priority", "review"],
    ["negotiable", "position_negotiable", "neutral"],
    ["fallback_positions", "position_fallback", "verified"],
  ];
  const populated = groups.filter(([key]) => (negotiation[key] || []).length);
  const questions = negotiation.client_questions || [];

  if (!populated.length && !questions.length) {
    return `<p class="bsf-caption">${esc(t("no_negotiation_position"))}</p>`;
  }
  return `
    <p class="bsf-caption">${esc(t("negotiation_caption"))}</p>
    ${populated.map(([key, labelKey, kind]) => `
      <div class="bsf-item">
        ${badge(t(labelKey), kind)}
        <ul>${negotiation[key].map((item) => `
          <li>${esc(typeof item === "string" ? item : JSON.stringify(item))}</li>`).join("")}</ul>
      </div>`).join("")}
    ${questions.length ? `
      <h4 class="bsf-subsection">${esc(t("questions_for_client"))}</h4>
      <ul>${questions.map((item) => `<li>${esc(typeof item === "string" ? item : (item.question || ""))}</li>`).join("")}</ul>` : ""}`;
}

function renderAgreementDiscussionTab(state) {
  const submit = region("agreement-ask-submit");
  if (submit) submit.textContent = t("send");

  const locked = region("agreement-discussion-locked");
  const form = document.querySelector('[data-form="agreement-ask"]');
  if (!state.review) {
    html(locked, alertBox(t("complete_review_first"), "warn"));
    if (form) form.querySelector("button").disabled = true;
  } else {
    html(locked, "");
    if (form) form.querySelector("button").disabled = false;
  }
}
/* ============================================================
   Source-page viewer
   ============================================================ */
function setModalVisible(visible) {
  const modal = document.getElementById("source-modal");
  if (!modal) return;
  // Both are needed: [hidden] alone loses to .bsf-modal's display:flex.
  modal.hidden = !visible;
  modal.style.display = visible ? "flex" : "none";
}

async function openSourcePage(pageId) {
  const body = region("modal-body");
  region("modal-title").textContent = t("source_page");
  html(body, `<p class="bsf-caption">${esc(t("loading"))}</p>`);
  setModalVisible(true);

  try {
    const meta = await apiGet("/page_text", { case_id: S.caseId, page_id: pageId });
    region("modal-title").textContent = meta.label || t("source_page");
    const imageUrl = backendUrl("/page_image") + "?" +
      new URLSearchParams({ case_id: S.caseId, page_id: pageId }).toString();
    html(body, `
      <img src="${esc(imageUrl)}" alt=""
           onerror="this.replaceWith(Object.assign(document.createElement('p'),
                    {className:'bsf-caption',textContent:${JSON.stringify(t("page_image_unavailable"))}}))">
      <h4 class="bsf-subsection">${esc(t("extracted_text_on_page"))}</h4>
      <pre>${esc(meta.text || "")}</pre>`);
  } catch (error) {
    html(body, alertBox(t("request_failed", { error: error.message }), "flag"));
  }
}

function closeModal() {
  setModalVisible(false);
}

/* ============================================================
   Action handlers, wired through one delegated click listener.
   ============================================================ */
const ACTIONS = {
  "open-case": (el) => openCase(el.dataset.caseId),

  "back-to-library": () => backToLibrary(),

  "close-modal": () => closeModal(),

  "remove-upload": (el) => removeUploadFile(el.dataset.kind, Number(el.dataset.index)),

  "view-page": (el) => openSourcePage(el.dataset.pageId),

  "flag": async (el) => {
    try {
      await apiPost("/flag", {
        case_id: S.caseId,
        entity_type: el.dataset.entityType,
        entity_id: el.dataset.entityId,
        action: el.dataset.flag,
      });
      toast(el.dataset.flag === "verified" ? t("verified_this_session") : t("flagged_for_review"), "ok");
      await refreshCase();
    } catch (error) { fail(error); }
  },

  "review-completeness": async () => {
    try {
      const result = await apiPost("/documents/review_completeness", { case_id: S.caseId });
      html(region("completeness-result"), alertBox(result.reply || "", "info"));
    } catch (error) { fail(error); }
  },

  "prepare-summary": async () => {
    try {
      await runJob(apiPost("/summary/prepare", { case_id: S.caseId }), "summary-job");
      await refreshCase();
    } catch (error) {
      await refreshCase();
      html(region("summary-body"), alertBox(t("summary_generation_failed", { error: error.message }), "flag"));
    }
  },

  "run-analysis": async () => {
    try {
      await runJob(apiPost("/analysis/run", { case_id: S.caseId }), "analysis-job");
      await refreshCase();
    } catch (error) {
      await refreshCase();
      html(region("analysis-body"), alertBox(t("legal_analysis_failed", { error: error.message }), "flag"));
    }
  },

  "defence-plan": async () => {
    try {
      await runJob(apiPost("/analysis/defence_plan", { case_id: S.caseId }), "analysis-job");
      await refreshCase();
    } catch (error) {
      await refreshCase();
      html(region("strategy-body"), alertBox(t("defence_planning_failed", { error: error.message }), "flag"));
    }
  },

  "generate-pleading": async () => {
    const instructions = ($("#pleading-instructions") || {}).value || "";
    try {
      await runJob(apiPost("/pleading/generate", { case_id: S.caseId, instructions }), "pleading-job");
      await refreshCase();
    } catch (error) {
      await refreshCase();
      html(region("pleading-body"), alertBox(t("pleading_generation_failed", { error: error.message }), "flag"));
    }
  },

  "reopen-pleading": async () => {
    try {
      await apiPost("/pleading/reopen", { case_id: S.caseId });
      await refreshCase();
    } catch (error) { fail(error); }
  },

  "restore-version": async (el) => {
    try {
      await apiPost("/pleading/restore_version", {
        case_id: S.caseId, version: Number(el.dataset.version),
      });
      S.compareVersion = null;
      await refreshCase();
    } catch (error) { fail(error); }
  },

  "download": (el) => {
    const url = backendUrl("/pleading/export") + "?" + new URLSearchParams({
      case_id: S.caseId, fmt: el.dataset.fmt, lang: el.dataset.lang,
    }).toString();
    window.open(url, "_blank");
  },

  "classify-agreement": async () => {
    try {
      await runJob(apiPost("/agreement/classify", { case_id: S.caseId }), "classify-job");
      await refreshCase();
    } catch (error) {
      html(region("classification-detected"), alertBox(t("classification_failed", { error: error.message }), "flag"));
    }
  },

  "extract-clauses": async () => {
    try {
      await runJob(apiPost("/agreement/extract_clauses", { case_id: S.caseId }), "clauses-job");
      await refreshCase();
    } catch (error) {
      html(region("clause-alerts"), alertBox(t("clause_extraction_failed", { error: error.message }), "flag"));
    }
  },

  "run-agreement-review": async () => {
    const instructions = ($("#agreement-instructions") || {}).value || "";
    try {
      await runJob(apiPost("/agreement/run_review", { case_id: S.caseId, instructions }),
        "agreement-review-job");
      await refreshCase();
    } catch (error) {
      html(region("agreement-review-body"),
        alertBox(t("agreement_review_failed", { error: error.message }), "flag"));
    }
  },

  "accounting-run-pipeline": async () => {
    const documentIds = S.accountingSelectedDocs ? Array.from(S.accountingSelectedDocs) : [];
    if (S.accountingSelectedDocs && !documentIds.length) { toast(t("no_value_selected"), "warn"); return; }
    try {
      const result = await runJob(
        apiPost("/accounting/run_auto_pipeline", { case_id: S.caseId, document_ids: documentIds }),
        "accounting-auto-job",
      );
      toast(t("extraction_completed", { count: result.rows_added || 0 }), "ok");
    } catch (error) { fail(error); }
    await refreshCase();
  },

  "accounting-clear": async () => {
    if (!window.confirm(t("clear_accounting_explainer"))) return;
    try {
      await apiPost("/accounting/clear", { case_id: S.caseId });
      S.accountingSelectedDocs = null;
      toast(t("accounting_data_cleared"), "ok");
      await refreshCase();
    } catch (error) { fail(error); }
  },

  "accounting-confirm-field": async (el) => {
    const rowId = el.dataset.rowId;
    const fieldName = el.dataset.fieldName;
    const wrap = el.closest(".bsf-conflict-field");
    const customInput = wrap ? wrap.querySelector('input[type="text"]') : null;
    const customValue = customInput ? customInput.value.trim() : "";
    const value = el.dataset.useSuggestion ? (el.dataset.value || "") : customValue;
    if (!value) { toast(t("no_value_selected"), "warn"); return; }
    let saved;
    try {
      saved = await apiPost("/accounting/correction", {
        case_id: S.caseId, row_id: rowId, field_name: fieldName, value, corrected_by: "attorney",
      });
      toast(t("correction_saved"), "ok");
    } catch (error) { fail(error); return; }

    // Last pending value answered: continue the accounting analysis from
    // where it stopped, with the instructions on screen (or last used).
    if (saved.ready_for_analysis) {
      const box = $("#accounting-instructions");
      const instructions = (box && box.value.trim()) || saved.instructions || "";
      toast(t("accounting_continue_auto"), "ok");
      await refreshCase();
      await ACTIONS["accounting-synthesize"](null, instructions);
      return;
    }
    await refreshCase();
  },

  "accounting-synthesize": async (el, presetInstructions) => {
    const instructions = presetInstructions !== undefined
      ? presetInstructions
      : (($("#accounting-instructions") || {}).value || "");
    try {
      await runJob(
        apiPost("/accounting/synthesize", { case_id: S.caseId, instructions }),
        "accounting-synthesize-job",
      );
    } catch (error) {
      html(region("accounting-findings"), alertBox(error.message || String(error), "flag"));
    }
    await refreshCase();
  },

  "goto-stage": (el) => {
    S.tab = el.dataset.stage;
    showTab("case", S.tab);
  },
};

/* ============================================================
   Form handlers
   ============================================================ */
const FORMS = {
  "create-case": async (form) => {
    const data = new FormData(form);
    try {
      const result = await apiPost("/create_case", {
        case_name: data.get("case_name"),
        language: data.get("language"),
        workflow_type: S.workspace,
      });
      form.reset();
      await loadCases();
      await openCase(result.case_id);
    } catch (error) { fail(error); }
  },

  "upload-documents": async (form) => {
    if (!S.uploads.documents.length) { toast(t("no_files_selected"), "warn"); return; }
    const data = new FormData();
    data.append("case_id", S.caseId);
    data.append("file_purpose", form.querySelector('[name="file_purpose"]').value);
    S.uploads.documents.forEach((file) => data.append("files", file, file.name));
    try {
      const result = await runJob(apiUpload("/documents/process", data), "upload-job");
      if (result.total && !result.usable) {
        // Pages were read but none could be extracted, so nothing reaches
        // the facts register or the attorney summary. Say so, and say why.
        const status = Object.entries(result.page_status || {})
          .map(([name, count]) => `${name} × ${count}`).join(", ");
        toast(t("no_pages_usable", { total: result.total, status: status || "—" }), "warn");
        (result.page_errors || []).forEach((reason) =>
          toast(t("extraction_reason", { reason }), "warn"));
      } else {
        toast(t("processing_summary", {
          files: result.files, usable: result.usable, total: result.total,
          facts: result.facts, issues: result.issues, parties: result.parties,
          events: result.events, requests: result.evidence_requests,
        }), "ok");
      }
      form.reset();
      clearUploadQueue("documents");
      await refreshCase();
    } catch (error) { fail(error); }
  },

  "approve-summary": async (form) => {
    const data = new FormData(form);
    try {
      const result = await apiPost("/summary/approve", {
        case_id: S.caseId,
        reviewer: data.get("reviewer"),
        comments: data.get("comments"),
      });
      toast(t("summary_approved_unlocked", {
        name: data.get("reviewer"), approval: result.approval_id,
      }), "ok");
      await refreshCase();
    } catch (error) { fail(error); }
  },

  "revise-pleading": async (form) => {
    const data = new FormData(form);
    try {
      await runJob(apiPost("/pleading/revise", {
        case_id: S.caseId, revision_request: data.get("revision_request"),
      }), "revise-job");
      form.reset();
      await refreshCase();
    } catch (error) {
      await refreshCase();
      html(region("pleading-body"), alertBox(t("pleading_revision_failed", { error: error.message }), "flag"));
    }
  },

  "finalise-pleading": async (form) => {
    const data = new FormData(form);
    try {
      await apiPost("/pleading/mark_final", {
        case_id: S.caseId, final_reviewer: data.get("final_reviewer"),
      });
      await refreshCase();
    } catch (error) { fail(error); }
  },

  "ask": async (form) => {
    const data = new FormData(form);
    const question = String(data.get("question") || "").trim();
    if (!question) return;
    const addToRecord = ($("#add-to-record") || {}).checked || false;

    // Optimistic echo so the question appears immediately, exactly as the
    // Streamlit chat did before the answer came back.
    region("chat").insertAdjacentHTML("beforeend",
      messageMarkup({ role: "user", content: question }));
    form.reset();

    try {
      await runJob(apiPost("/discussion/ask", {
        case_id: S.caseId,
        conversation_id: S.caseId,
        question,
        add_to_record: addToRecord,
      }), "discussion-job");
      const checkbox = $("#add-to-record");
      if (checkbox) checkbox.checked = false;
      await refreshCase();
    } catch (error) {
      html(region("discussion-job"), alertBox(t("discussion_failed", { error: error.message }), "flag"));
    }
  },

  "upload-agreement": async (form) => {
    if (!S.uploads.agreement.length) { toast(t("no_files_selected"), "warn"); return; }
    const data = new FormData();
    data.append("case_id", S.caseId);
    data.append("zoom", form.querySelector('[name="zoom"]').value);
    S.uploads.agreement.forEach((file) => data.append("files", file, file.name));
    try {
      await runJob(apiUpload("/agreement/process", data), "agreement-upload-job");
      toast(t("agreement_documents_processed"), "ok");
      form.reset();
      clearUploadQueue("agreement");
      await refreshCase();
    } catch (error) { fail(error); }
  },

  "confirm-classification": async (form) => {
    const data = new FormData(form);
    try {
      await apiPost("/agreement/confirm_classification", {
        case_id: S.caseId,
        agreement_type: data.get("agreement_type"),
        relationship_type: data.get("relationship_type"),
        represented_party: data.get("represented_party"),
        counterparty: data.get("counterparty"),
        review_objective: data.get("review_objective"),
      });
      toast(t("classification_confirmed"), "ok");
      await refreshCase();
    } catch (error) { fail(error); }
  },

  "agreement-ask": async (form) => {
    const data = new FormData(form);
    const question = String(data.get("question") || "").trim();
    if (!question) return;
    region("agreement-chat").insertAdjacentHTML("beforeend",
      messageMarkup({ role: "user", content: question }));
    form.reset();
    try {
      const result = await runJob(apiPost("/agreement/discuss", {
        case_id: S.caseId, question,
      }), "agreement-discussion-job");
      region("agreement-chat").insertAdjacentHTML("beforeend",
        `<div class="bsf-msg bsf-msg-assistant">${answerMarkup(result.answer || {})}</div>`);
    } catch (error) { fail(error); }
  },
};

/* ============================================================
   Event wiring — delegated, so re-rendered markup stays live.
   ============================================================ */
function wireEvents() {
  setModalVisible(false);
  document.addEventListener("click", (event) => {
    const langBtn = event.target.closest("[data-lang]:not([data-action])");
    if (langBtn && langBtn.classList.contains("bsf-seg-btn")) {
      S.lang = langBtn.dataset.lang;
      applyLanguage();
      renderSidebar();
      if (S.view === "library") renderLibrary();
      else if (S.view === "case") renderCase();
      else renderAgreement();
      return;
    }

    const workspaceBtn = event.target.closest("[data-workspace]");
    if (workspaceBtn) {
      S.workspace = workspaceBtn.dataset.workspace;
      S.caseId = null;
      S.snapshot = null;
      showView("library");
      applyLanguage();
      loadCases();
      return;
    }

    const tabBtn = event.target.closest("[data-tab]");
    if (tabBtn) {
      const tabset = tabBtn.closest("[data-tabset]").dataset.tabset;
      if (tabset === "case") { S.tab = tabBtn.dataset.tab; showTab("case", S.tab); }
      else { S.agreementTab = tabBtn.dataset.tab; showTab("agreement", S.agreementTab); }
      return;
    }

    const actionEl = event.target.closest("[data-action]");
    if (actionEl && ACTIONS[actionEl.dataset.action]) {
      event.preventDefault();
      ACTIONS[actionEl.dataset.action](actionEl);
    }
  });

  document.addEventListener("submit", (event) => {
    const form = event.target.closest("[data-form]");
    if (!form) return;
    event.preventDefault();
    const handler = FORMS[form.dataset.form];
    if (handler) handler(form);
  });

  document.addEventListener("change", (event) => {
    const fileInput = event.target;
    if (fileInput.matches && fileInput.matches('input[type="file"]')) {
      const form = fileInput.closest("[data-form]");
      const kind = form && form.dataset.form === "upload-agreement" ? "agreement" : "documents";
      addUploadFiles(kind, fileInput.files);
      // Clearing lets the picker re-offer a file the user removed.
      fileInput.value = "";
      return;
    }

    const versionSelect = event.target.closest('[data-action="select-version"]');
    if (versionSelect) {
      S.compareVersion = Number(versionSelect.value);
      renderPleadingTab();
      return;
    }

    const docToggle = event.target.closest('[data-action="toggle-accounting-doc"]');
    if (docToggle) {
      if (!S.accountingSelectedDocs) S.accountingSelectedDocs = new Set();
      if (docToggle.checked) S.accountingSelectedDocs.add(docToggle.value);
      else S.accountingSelectedDocs.delete(docToggle.value);
    }
  });

  // Debounced search inputs.
  bindSearch("#library-search", (value) => { S.libraryQuery = value; loadCases(); });
  bindSearch("#case-search", (value) => { S.caseQuery = value; renderCaseSearch(); });
  bindSearch("#facts-filter", (value) => { S.factsFilter = value; renderFactsRegister(); });
  bindSearch("#clause-filter", (value) => {
    S.clauseFilter = value;
    if (S.snapshot) renderClauseTab(S.snapshot.agreement_state || {});
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeModal();
  });
}

function bindSearch(selector, handler) {
  const input = document.querySelector(selector);
  if (!input) return;
  let timer;
  input.addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(() => handler(input.value), 250);
  });
}

/* ============================================================
   Boot
   ============================================================ */
async function init() {
  wireEvents();
  applyLanguage();
  showView("library");
  showTab("case", S.tab);
  showTab("agreement", S.agreementTab);

  try {
    S.bootstrap = await apiGet("/bootstrap");
    if (S.bootstrap.logo) {
      const logo = document.getElementById("app-logo");
      logo.src = S.bootstrap.logo;
      logo.hidden = false;
    }
  } catch (error) {
    // A missing logo or asset folder must not block the workbench.
    console.warn("bootstrap failed", error);
  }

  await loadCases();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}

