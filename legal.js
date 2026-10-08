
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
    "column_name": "Name",
    "column_related_evidence_pages": "Related evidence pages",
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
    "download_pleading_docx": "Download pleading (.docx)",
    "pleading_language": "Pleading language",
    "pleading_language_en": "English",
    "pleading_language_ar": "Arabic — العربية",
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
    "no_issue_with_authority": "No issue is supported by retrieved knowledge-base text yet.",
    "issues_without_authority": "Issues without retrieved authority ({count})",
    "issues_without_authority_note": "No retrieved text or authority nodes were found for these issues, so they are not analysed legally here and remain for attorney review.",
    "issues_not_analysed": "Issues not analysed ({count})",
    "issues_not_analysed_note": "The model's answer for these issues could not be read. Run the legal analysis again.",
    "marked_agreement": "The agreement with the proposed changes",
    "marked_caption": "The words in red should change; the arrow shows how they should read instead. Hover a change to see why.",
    "marked_page": "{file} — page {page}",
    "marked_changes": "{count} change(s)",
    "marked_no_change": "no change",
    "marked_delete": "delete",
    "marked_add": "add",
    "marked_unplaced": "Changes whose words were not found on the pages",
    "proposed_changes": "Proposed changes to the wording",
    "contract_with_changes": "The contract with the proposed changes",
    "contract_changes_caption": "{count} change(s) in the text. Hover over a change to see why.",
    "contract_legend_old": "wording to change or remove",
    "contract_legend_new": "proposed wording",
    "download_contract_docx": "Download Word (.docx)",
    "contract_docx_note": "In Word the changes are tracked changes: accept or reject each one; the reason is in its comment.",
    "contract_page": "Page {page}",
    "contract_other_changes": "Other proposed changes",
    "contract_other_caption": "These words were not found exactly in the extracted text, so they are listed here instead of placed in it.",
    "contract_no_edits": "This review was made before changes were marked in the contract. Run the review again to see them in the text and in Word.",
    "review_details": "Review details (summary, clause-by-clause findings, negotiation)",
    "no_clause_text": "No text captured for this clause.",
    "no_dated_events": "No dated events were identified.",
    "no_english_summary": "A separate English summary was not generated. Refresh the attorney summary.",
    "no_exposure_points": "No legal exposure points recorded.",
    "no_facts_extracted": "No facts have been extracted yet. Process documents above first.",
    "no_matching_agreements": "No matching agreement files",
    "no_matching_cases": "No matching litigation cases",
    "no_negotiation_position": "No negotiation position was generated for this review yet — re-run the review above once clause reviews are available.",
    "no_pages_extracted": "No pages were extracted from {name}.",
    "no_parties_confirmed": "No parties were confirmed in the current summary.",
    "no_search_matches": "No matches yet — try a different term.",
    "no_summary_generated": "No consolidated summary has been generated in this session.",
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
    "column_name": "الاسم",
    "column_related_evidence_pages": "صفحات الأدلة المرتبطة",
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
    "download_pleading_docx": "تنزيل المذكرة (.docx)",
    "pleading_language": "لغة المذكرة",
    "pleading_language_en": "English — الإنجليزية",
    "pleading_language_ar": "العربية",
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
    "no_issue_with_authority": "لا توجد مسألة يسندها نص مسترجع من قاعدة المعرفة حتى الآن.",
    "issues_without_authority": "مسائل بلا سند نظامي مسترجع ({count})",
    "issues_without_authority_note": "لم يُعثر على نصوص مسترجعة أو عُقد سند نظامي لهذه المسائل، لذا لا تُحلل قانونياً هنا وتبقى لمراجعة المحامي.",
    "issues_not_analysed": "مسائل لم يكتمل تحليلها ({count})",
    "issues_not_analysed_note": "تعذّرت قراءة إجابة النموذج لهذه المسائل. أعد تشغيل التحليل القانوني.",
    "marked_agreement": "الاتفاقية مع التعديلات المقترحة",
    "marked_caption": "العبارات باللون الأحمر يجب تعديلها، والسهم يبيّن الصياغة الصحيحة. مرّر المؤشر على التعديل لمعرفة السبب.",
    "marked_page": "{file} — صفحة {page}",
    "marked_changes": "{count} تعديل",
    "marked_no_change": "بلا تعديل",
    "marked_delete": "حذف",
    "marked_add": "إضافة",
    "marked_unplaced": "تعديلات لم يُعثر على عباراتها في الصفحات",
    "proposed_changes": "التعديلات المقترحة على الصياغة",
    "contract_with_changes": "العقد مع التعديلات المقترحة",
    "contract_changes_caption": "{count} تعديل في النص. مرّر المؤشر على التعديل لمعرفة سببه.",
    "contract_legend_old": "صياغة يجب تعديلها أو حذفها",
    "contract_legend_new": "الصياغة المقترحة",
    "download_contract_docx": "تنزيل ملف Word (.docx)",
    "contract_docx_note": "في ملف Word تظهر التعديلات كتعديلات متعقّبة: اقبل أو ارفض كل تعديل، وسببه في التعليق المرفق.",
    "contract_page": "صفحة {page}",
    "contract_other_changes": "تعديلات مقترحة أخرى",
    "contract_other_caption": "لم يُعثر على هذه العبارات حرفياً في النص المستخرج، لذا أُدرجت هنا بدلاً من وضعها في النص.",
    "contract_no_edits": "أُجريت هذه المراجعة قبل إضافة التعديلات داخل نص العقد. أعد تشغيل المراجعة لتظهر في النص وفي ملف Word.",
    "review_details": "تفاصيل المراجعة (الملخص، نتائج كل بند، التفاوض)",
    "no_clause_text": "لم يُلتقط نص لهذا البند.",
    "no_dated_events": "لم تُحدد أي أحداث مؤرخة.",
    "no_english_summary": "لم يتم إنشاء ملخص إنجليزي مستقل. أعد إعداد ملخص المحامي.",
    "no_exposure_points": "لا توجد نقاط تعرض قانوني مسجلة.",
    "no_facts_extracted": "لم تُستخرج أي وقائع بعد. عالج المستندات أعلاه أولاً.",
    "no_matching_agreements": "لا توجد ملفات اتفاقيات مطابقة",
    "no_matching_cases": "لا توجد قضايا مطابقة",
    "no_negotiation_position": "لم يُنشأ موقف تفاوضي لهذه المراجعة بعد — أعد تشغيل المراجعة أعلاه بعد توفر مراجعات البنود.",
    "no_pages_extracted": "لم تُستخرج أي صفحات من {name}.",
    "no_parties_confirmed": "لم تُعتمد أي أطراف في الملخص الحالي.",
    "no_search_matches": "لا توجد نتائج مطابقة — جرّب مصطلحاً آخر.",
    "no_summary_generated": "لم يُنشأ ملخص موحد في هذه الجلسة.",
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
  status_completed: "Done",
  status_not_yet: "Not yet",
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
  detail_review_items: "{count} fact(s) need your review before the accounting analysis can continue.",
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
  accounting_continue_auto: "All facts reviewed — continuing the accounting analysis…",
  report_line: "{financial} of {scope} page(s) are financial · {rows} new row(s) extracted · {pending} value(s) awaiting you",
  report_failures: "{count} page(s) could not be processed. Run the extraction again to retry them.",
  report_discarded: "{count} zero-amount line(s) were ignored as balance or heading rows.",
  ledger_withheld: "{count} uncertain fact(s) are held back from the ledger until you review them.",
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
  fact_status_EXTRACTED: "Extracted",
  fact_status_CALCULATED: "Calculated",
  fact_status_INFERRED: "Inferred",
  fact_status_UNCERTAIN: "Uncertain",
  fact_status_MISSING: "Missing",
  fact_status_USER_CONFIRMED: "Confirmed by you",
  fact_status_USER_CORRECTED: "Corrected by you",
  fact_status_IGNORED: "Ignored",
  fact_type_transaction: "Transaction",
  fact_type_payment: "Payment",
  fact_type_installment: "Installment",
  fact_type_deposit: "Deposit",
  fact_type_withdrawal: "Withdrawal",
  fact_type_transfer: "Transfer",
  fact_type_financing_amount: "Financing amount",
  fact_type_outstanding_balance: "Outstanding balance",
  fact_type_remaining_balance: "Remaining balance",
  fact_type_amount_due: "Amount due",
  fact_type_opening_balance: "Opening balance",
  fact_type_closing_balance: "Closing balance",
  fact_type_balance: "Balance",
  fact_type_fee: "Fee",
  fact_type_interest: "Interest",
  fact_type_penalty: "Penalty",
  fact_type_credit_limit: "Credit limit",
  fact_type_claimed_amount: "Claimed amount",
  fact_type_other: "Other",
  field_fact_type: "Fact type",
  field_debit: "Debit",
  field_credit: "Credit",
  field_balance: "Balance",
  field_amount_due: "Amount due",
  field_paid_amount: "Paid amount",
  field_remaining_amount: "Remaining amount",
  field_account_number: "Account number",
  field_transaction_reference: "Reference",
  field_counterparty: "Counterparty",
  column_fact_type: "Fact",
  column_value: "Value",
  column_debit: "Debit",
  column_credit: "Credit",
  column_balance: "Balance",
  fact_review_heading: "Facts waiting for your review",
  fact_review_count: "{count} fact(s) need your review before the accounting analysis can run.",
  fact_item_title: "{page} — {type}",
  fact_ai_interpretation: "AI interpretation",
  fact_question: "Question",
  fact_alternatives: "Other possible meanings",
  fact_calc_failed: "Calculation check",
  fact_confirm: "Confirm",
  fact_ignore: "Ignore",
  fact_correct: "Correct",
  fact_save_correction: "Save correction",
  fact_explain_label: "Or explain how to read it (the AI will rewrite the fact for you to confirm)",
  fact_explain_placeholder: "e.g. This is actually the amount of the third installment.",
  fact_apply_explanation: "Apply explanation",
  fact_proposal_heading: "AI rewrite based on your explanation",
  fact_accept_proposal: "Accept rewrite",
  fact_note_label: "Note (optional)",
  fact_explaining: "Applying your explanation…",
  fact_saved: "Decision saved.",
  fact_ignore_confirm: "Leave this fact out of the ledger?",
  review_prev: "‹ Previous",
  review_next: "Next ›",
  review_page_of: "Page {page} of {pages} · {total} fact(s) to review",
  review_confirm_page: "Confirm all on this page ({count})",
  review_confirm_page_prompt: "Confirm the {count} fact(s) on this page exactly as the AI interpreted them?",
  ledger_note: "Note: {note}",
  claim_parent: "From claim: {text}",
  claimed_amount_label: "Claimed",
  substantiated_amount_label: "Substantiated",
  evidence_total_label: "Total of cited evidence",
  accounting_position_label: "Accounting position",
  supporting_evidence_label: "Supporting evidence",
  partially_supporting_evidence_label: "Partially supporting evidence",
  contradicting_evidence_label: "Contradicting evidence",
  unresolved_evidence_label: "Unresolved / ambiguous evidence",
});
Object.assign(I18N.ar, {
  step_accounting: "التحليل المحاسبي",
  step_discussion: "مساعد القضية",
  status_not_started: "لم تبدأ",
  status_blocked: "بانتظار الخطوات السابقة",
  status_running: "قيد المعالجة",
  status_waiting_for_user: "بانتظارك",
  status_ready: "جاهزة للمتابعة",
  status_completed: "تمت",
  status_not_yet: "لم تتم بعد",
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
  detail_review_items: "{count} واقعة تحتاج إلى مراجعتك قبل متابعة التحليل المحاسبي.",
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
  accounting_continue_auto: "تمت مراجعة جميع الوقائع — جارٍ متابعة التحليل المحاسبي…",
  report_line: "{financial} من {scope} صفحة مالية · {rows} بند جديد مستخرج · {pending} قيمة بانتظارك",
  report_failures: "تعذّرت معالجة {count} صفحة. شغّل الاستخراج مرة أخرى لإعادة المحاولة.",
  report_discarded: "تم تجاهل {count} سطر بمبلغ صفري باعتبارها أرصدة أو عناوين.",
  ledger_withheld: "{count} واقعة غير مؤكدة محجوبة عن السجل المالي حتى تراجعها.",
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
  fact_status_EXTRACTED: "مستخرجة",
  fact_status_CALCULATED: "محسوبة",
  fact_status_INFERRED: "مستنتجة",
  fact_status_UNCERTAIN: "غير مؤكدة",
  fact_status_MISSING: "غير موجودة",
  fact_status_USER_CONFIRMED: "أكدتها",
  fact_status_USER_CORRECTED: "صححتها",
  fact_status_IGNORED: "مستبعدة",
  fact_type_transaction: "معاملة",
  fact_type_payment: "سداد",
  fact_type_installment: "قسط",
  fact_type_deposit: "إيداع",
  fact_type_withdrawal: "سحب",
  fact_type_transfer: "تحويل",
  fact_type_financing_amount: "مبلغ التمويل",
  fact_type_outstanding_balance: "الرصيد القائم",
  fact_type_remaining_balance: "الرصيد المتبقي",
  fact_type_amount_due: "المبلغ المستحق",
  fact_type_opening_balance: "الرصيد الافتتاحي",
  fact_type_closing_balance: "الرصيد الختامي",
  fact_type_balance: "الرصيد",
  fact_type_fee: "رسوم",
  fact_type_interest: "فوائد",
  fact_type_penalty: "غرامة",
  fact_type_credit_limit: "حد ائتماني",
  fact_type_claimed_amount: "المبلغ المطالب به",
  fact_type_other: "أخرى",
  field_fact_type: "نوع الواقعة",
  field_debit: "مدين",
  field_credit: "دائن",
  field_balance: "الرصيد",
  field_amount_due: "المبلغ المستحق",
  field_paid_amount: "المبلغ المسدد",
  field_remaining_amount: "المبلغ المتبقي",
  field_account_number: "رقم الحساب",
  field_transaction_reference: "المرجع",
  field_counterparty: "الطرف المقابل",
  column_fact_type: "الواقعة",
  column_value: "القيمة",
  column_debit: "مدين",
  column_credit: "دائن",
  column_balance: "الرصيد",
  fact_review_heading: "وقائع بانتظار مراجعتك",
  fact_review_count: "{count} واقعة تحتاج إلى مراجعتك قبل تشغيل التحليل المحاسبي.",
  fact_item_title: "{page} — {type}",
  fact_ai_interpretation: "تفسير الذكاء الاصطناعي",
  fact_question: "السؤال",
  fact_alternatives: "معانٍ محتملة أخرى",
  fact_calc_failed: "التحقق من الحساب",
  fact_confirm: "تأكيد",
  fact_ignore: "استبعاد",
  fact_correct: "تصحيح",
  fact_save_correction: "حفظ التصحيح",
  fact_explain_label: "أو اشرح كيف تُقرأ (سيعيد الذكاء الاصطناعي صياغة الواقعة لتأكيدها)",
  fact_explain_placeholder: "مثال: هذا في الواقع مبلغ القسط الثالث.",
  fact_apply_explanation: "تطبيق الشرح",
  fact_proposal_heading: "إعادة صياغة بناءً على شرحك",
  fact_accept_proposal: "قبول الصياغة",
  fact_note_label: "ملاحظة (اختياري)",
  fact_explaining: "جارٍ تطبيق شرحك…",
  fact_saved: "تم حفظ القرار.",
  fact_ignore_confirm: "استبعاد هذه الواقعة من السجل المالي؟",
  review_prev: "‹ السابق",
  review_next: "التالي ›",
  review_page_of: "صفحة {page} من {pages} · {total} واقعة للمراجعة",
  review_confirm_page: "تأكيد كل ما في هذه الصفحة ({count})",
  review_confirm_page_prompt: "تأكيد {count} واقعة في هذه الصفحة كما فسّرها الذكاء الاصطناعي؟",
  ledger_note: "ملاحظة: {note}",
  claim_parent: "من المطالبة: {text}",
  claimed_amount_label: "المطالب به",
  substantiated_amount_label: "الثابت بالأدلة",
  evidence_total_label: "مجموع الأدلة المستشهد بها",
  accounting_position_label: "الموقف المحاسبي",
  supporting_evidence_label: "أدلة داعمة",
  partially_supporting_evidence_label: "أدلة داعمة جزئياً",
  contradicting_evidence_label: "أدلة مناقضة",
  unresolved_evidence_label: "أدلة غير محسومة / ملتبسة",
});

const LANGUAGES = { en: "English", ar: "العربية" };

/// Added by Youssif for Monitoring Purposes ///
const SESSION_ID = (crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) + Math.random());
/// END ///

/* Personal workspace: dashboard and case workspace. */
Object.assign(I18N.en, {
  nav_dashboard: "My dashboard",
  back_to_dashboard: "Back to my dashboard",
  signed_in_with_dataiku: "Signed in",
  sign_in_required: "Please sign in to Dataiku to use the workbench.",
  dash_title: "My workspace",
  dash_welcome: "Welcome, {user}",
  dash_caption: "Your litigation cases and contract reviews. Only you can see them.",
  dash_metric_cases: "Active cases",
  dash_metric_attention: "Waiting for your review",
  dash_metric_completed: "Completed",
  dash_metric_contracts: "Contract reviews",
  my_litigation_cases: "My litigation cases",
  my_contract_reviews: "My contract reviews",
  new_litigation_case: "+ New litigation case",
  new_contract_review: "+ New contract review",
  filter_all_statuses: "All stages",
  show_archived: "Show archived",
  progress_new: "New",
  progress_documents_uploaded: "Documents uploaded",
  progress_processing: "Processing",
  progress_accounting_review: "Accounting review",
  progress_legal_analysis: "Legal analysis",
  progress_attorney_review: "Attorney review",
  progress_ready_for_pleading: "Ready for pleading",
  progress_completed: "Completed",
  col_case_name: "Case name",
  col_case_number: "Case number",
  col_parties: "Client / opposing party",
  col_case_type: "Case type",
  col_last_updated: "Last updated",
  col_stage: "Stage",
  col_status: "Status",
  col_contract_name: "Contract name",
  col_contract_type: "Contract type",
  col_counterparty: "Counterparty",
  continue_case: "Continue",
  continue_review: "Continue",
  archive_case: "Archive",
  restore_case: "Restore",
  archive_confirm: "Archive this case? It leaves your dashboard and can be restored from \"Show archived\".",
  case_archived: "Case archived.",
  case_restored: "Case restored.",
  no_cases_yet: "No litigation cases yet. Create one to start.",
  no_archived_cases: "No archived cases.",
  no_contracts_yet: "No contract reviews yet.",
  no_archived_contracts: "No archived contract reviews.",
  field_case_number: "Case number",
  field_client: "Client",
  field_opposing_party: "Opposing party",
  field_description_optional: "Description (optional)",
  create_case_and_upload: "Create case and add documents",
  create_contract_review: "Create contract review",
  last_updated_at: "Last updated {at}",
  case_progress: "Case progress",
  go_there: "Go",
  metric_financial_pages: "Financial documents (pages)",
  metric_financial_claims: "Financial claims",
  metric_atomic_facts: "Atomic financial facts",
  metric_pending_reviews: "Pending reviews",
  col_file: "File",
  col_pages: "Pages",
  col_document_type: "Document type",
  col_reading: "Reading",
  col_accounting: "Used in accounting",
  doc_pages_failed: "{count} page(s) could not be read",
  doc_pages_to_check: "{count} page(s) to check",
  doc_read_ok: "Read",
  doc_not_checked_yet: "Not checked yet",
  doc_financial_pages: "{count} financial page(s), {facts} fact(s)",
  doc_no_financial_records: "No financial records",
  preview: "Preview",
  tab_home: "Overview",
  tab_documents: "Documents & facts",
  tab_accounting: "Accounting analysis",
  tab_attorney_review: "Attorney review",
  tab_legal_analysis: "Legal analysis",
  tab_written_pleading: "Written pleading",
  tab_case_discussion: "Case assistant",
});

Object.assign(I18N.ar, {
  nav_dashboard: "لوحتي",
  back_to_dashboard: "العودة إلى لوحتي",
  signed_in_with_dataiku: "مسجّل الدخول",
  sign_in_required: "يرجى تسجيل الدخول إلى Dataiku لاستخدام المنصة.",
  dash_title: "مساحة عملي",
  dash_welcome: "مرحبًا، {user}",
  dash_caption: "قضاياك ومراجعات عقودك. لا يراها أحد غيرك.",
  dash_metric_cases: "القضايا النشطة",
  dash_metric_attention: "بانتظار مراجعتك",
  dash_metric_completed: "مكتملة",
  dash_metric_contracts: "مراجعات العقود",
  my_litigation_cases: "قضاياي",
  my_contract_reviews: "مراجعات عقودي",
  new_litigation_case: "+ قضية جديدة",
  new_contract_review: "+ مراجعة عقد جديدة",
  filter_all_statuses: "جميع المراحل",
  show_archived: "عرض المؤرشفة",
  progress_new: "جديدة",
  progress_documents_uploaded: "تم رفع المستندات",
  progress_processing: "قيد المعالجة",
  progress_accounting_review: "المراجعة المحاسبية",
  progress_legal_analysis: "التحليل القانوني",
  progress_attorney_review: "مراجعة المحامي",
  progress_ready_for_pleading: "جاهزة للمذكرة",
  progress_completed: "مكتملة",
  col_case_name: "اسم القضية",
  col_case_number: "رقم القضية",
  col_parties: "العميل / الخصم",
  col_case_type: "نوع القضية",
  col_last_updated: "آخر تحديث",
  col_stage: "المرحلة",
  col_status: "الحالة",
  col_contract_name: "اسم العقد",
  col_contract_type: "نوع العقد",
  col_counterparty: "الطرف الآخر",
  continue_case: "متابعة",
  continue_review: "متابعة",
  archive_case: "أرشفة",
  restore_case: "استعادة",
  archive_confirm: "أرشفة هذه القضية؟ ستختفي من لوحتك ويمكن استعادتها من «عرض المؤرشفة».",
  case_archived: "تمت أرشفة القضية.",
  case_restored: "تمت استعادة القضية.",
  no_cases_yet: "لا توجد قضايا بعد. أنشئ قضية للبدء.",
  no_archived_cases: "لا توجد قضايا مؤرشفة.",
  no_contracts_yet: "لا توجد مراجعات عقود بعد.",
  no_archived_contracts: "لا توجد مراجعات عقود مؤرشفة.",
  field_case_number: "رقم القضية",
  field_client: "العميل",
  field_opposing_party: "الخصم",
  field_description_optional: "الوصف (اختياري)",
  create_case_and_upload: "إنشاء القضية وإضافة المستندات",
  create_contract_review: "إنشاء مراجعة العقد",
  last_updated_at: "آخر تحديث {at}",
  case_progress: "سير القضية",
  go_there: "انتقال",
  metric_financial_pages: "المستندات المالية (صفحات)",
  metric_financial_claims: "الادعاءات المالية",
  metric_atomic_facts: "الوقائع المالية الذرية",
  metric_pending_reviews: "مراجعات معلّقة",
  col_file: "الملف",
  col_pages: "الصفحات",
  col_document_type: "نوع المستند",
  col_reading: "القراءة",
  col_accounting: "مستخدم في المحاسبة",
  doc_pages_failed: "تعذّرت قراءة {count} صفحة",
  doc_pages_to_check: "{count} صفحة للتحقق",
  doc_read_ok: "تمت القراءة",
  doc_not_checked_yet: "لم يُفحص بعد",
  doc_financial_pages: "{count} صفحة مالية، {facts} واقعة",
  doc_no_financial_records: "لا توجد سجلات مالية",
  preview: "معاينة",
  tab_home: "نظرة عامة",
  tab_documents: "المستندات والوقائع",
  tab_accounting: "التحليل المحاسبي",
  tab_attorney_review: "مراجعة المحامي",
  tab_legal_analysis: "التحليل القانوني",
  tab_written_pleading: "المذكرة المكتوبة",
  tab_case_discussion: "مساعد القضية",
});

/* Financial fact review (page beside the table). */
Object.assign(I18N.en, {
  review_claims_heading: "Financial claims found in these pages ({count}) — to verify, not evidence",
  review_claims_caption: "What emails and narrative sections say about money. They are not accounting facts and are not in the ledger; the accounting analysis checks them against the records above.",
  review_claim_statement: "Statement",
  review_claim_by: "Made by",
  review_claim_amounts: "Amounts mentioned",
  review_source_type: "Record: {type}",
  continue_to_written_pleading: "Continue to the written pleading",
  review_heading: "Financial facts — review page by page",
  review_caption: "The page is shown beside the table; its rows are highlighted. Click any cell to correct it (Enter saves, Esc cancels). Your edits are kept and the AI's reading stays visible.",
  review_uncertain_count: "{count} value(s) are uncertain (marked in red): the readings of the page disagreed. Check them against the page.",
  review_confirmed_by: "Facts confirmed by {by} on {at}. Edits made since then are kept; the analysis shows when it is out of date.",
  review_page_position: "page {index} of {total}",
  review_open_full_page: "Open the full page",
  review_extraction_heading: "Page {page} — what was extracted",
  review_no_facts_on_page: "No financial facts were extracted from this page. Add one below if the page holds one.",
  review_previous_page: "Previous page",
  review_next_page: "Next page",
  review_confirm_all: "Confirm all pages",
  review_confirm_again: "Confirm all pages again",
  review_confirm_all_prompt: "Confirm all {count} facts as shown? {uncertain} uncertain value(s) will be accepted as they are now. The accounting analysis can then run.",
  review_confirmed_toast: "All pages confirmed. You can run the accounting analysis.",
  review_cell_edited: "AI read: {value} — edited by {by}",
  review_cell_click_to_edit: "Click to edit",
  review_you: "you",
  review_added_by_you: "Added by you",
  review_edited_by_you: "Edited by you",
  review_confirmed: "Confirmed",
  review_from_ai: "AI extraction",
  review_as_printed: "As printed",
  review_restore: "Restore",
  review_delete_title: "Remove this fact from the ledger",
  review_delete_confirm: "Remove this fact from the ledger? It stays on record and can be restored.",
  review_add_fact: "+ Add a fact on page {page}",
  review_add_save: "Add",
  review_fact_added: "Fact added.",
  review_route_native: "From the PDF's own text",
  review_route_mixed: "PDF text + pictures read by the vision model",
  review_route_vlm: "Read from the page image",
  review_kind_photo: "Camera photo",
  review_kind_scan: "Scan",
  review_kind_screenshot: "Screenshot / digital",
  review_flag_low_resolution: "low resolution",
  review_flag_table_heavy: "table",
  review_flag_mixed: "text and table",
  review_candidates: "Readings merged: {names}",
  review_extraction_uncertain: "Values the readings disagreed on",
  review_extracted_text: "Extracted text",
  review_extraction_errors: "{count} extraction note(s)",
  detail_confirm_facts: "Review the financial facts and press \u201cConfirm all pages\u201d to continue.",
});

Object.assign(I18N.ar, {
  review_claims_heading: "ادعاءات مالية وردت في هذه الصفحات ({count}) — للتحقق وليست أدلة",
  review_claims_caption: "ما تذكره الرسائل والأجزاء السردية عن المبالغ. ليست وقائع محاسبية ولا تدخل في السجل؛ يتحقق منها التحليل المحاسبي مقابل السجلات أعلاه.",
  review_claim_statement: "العبارة",
  review_claim_by: "صادرة عن",
  review_claim_amounts: "المبالغ المذكورة",
  review_source_type: "السجل: {type}",
  continue_to_written_pleading: "متابعة إلى المذكرة المكتوبة",
  review_heading: "الوقائع المالية — المراجعة صفحةً صفحة",
  review_caption: "تظهر الصفحة بجانب الجدول مع تمييز صفوفها. انقر على أي خلية لتصحيحها (Enter للحفظ وEsc للإلغاء). تُحفظ تعديلاتك وتبقى قراءة الذكاء الاصطناعي ظاهرة.",
  review_uncertain_count: "{count} قيمة غير مؤكدة (باللون الأحمر): اختلفت قراءات الصفحة. تحقق منها مقابل الصفحة.",
  review_confirmed_by: "أكّد {by} الوقائع بتاريخ {at}. التعديلات اللاحقة محفوظة، ويُشار إلى التحليل إذا أصبح غير محدّث.",
  review_page_position: "الصفحة {index} من {total}",
  review_open_full_page: "فتح الصفحة كاملة",
  review_extraction_heading: "الصفحة {page} — ما تم استخراجه",
  review_no_facts_on_page: "لم تُستخرج وقائع مالية من هذه الصفحة. أضف واقعة أدناه إن كانت الصفحة تتضمن واحدة.",
  review_previous_page: "الصفحة السابقة",
  review_next_page: "الصفحة التالية",
  review_confirm_all: "تأكيد جميع الصفحات",
  review_confirm_again: "تأكيد جميع الصفحات مجددًا",
  review_confirm_all_prompt: "تأكيد جميع الوقائع ({count}) كما هي معروضة؟ ستُقبل {uncertain} قيمة غير مؤكدة بحالتها الحالية، ثم يمكن تشغيل التحليل المحاسبي.",
  review_confirmed_toast: "تم تأكيد جميع الصفحات. يمكنك تشغيل التحليل المحاسبي.",
  review_cell_edited: "قراءة الذكاء الاصطناعي: {value} — عدّلها {by}",
  review_cell_click_to_edit: "انقر للتعديل",
  review_you: "أنت",
  review_added_by_you: "أضفتها أنت",
  review_edited_by_you: "عدّلتها أنت",
  review_confirmed: "مؤكدة",
  review_from_ai: "استخراج آلي",
  review_as_printed: "كما وردت في المستند",
  review_restore: "استعادة",
  review_delete_title: "استبعاد هذه الواقعة من السجل",
  review_delete_confirm: "استبعاد هذه الواقعة من السجل؟ تبقى محفوظة ويمكن استعادتها.",
  review_add_fact: "+ إضافة واقعة في الصفحة {page}",
  review_add_save: "إضافة",
  review_fact_added: "تمت إضافة الواقعة.",
  review_route_native: "من نص ملف PDF نفسه",
  review_route_mixed: "نص PDF مع صور قرأها نموذج الرؤية",
  review_route_vlm: "مقروءة من صورة الصفحة",
  review_kind_photo: "صورة بالكاميرا",
  review_kind_scan: "مسح ضوئي",
  review_kind_screenshot: "لقطة شاشة / رقمية",
  review_flag_low_resolution: "دقة منخفضة",
  review_flag_table_heavy: "جدول",
  review_flag_mixed: "نص وجدول",
  review_candidates: "القراءات المدمجة: {names}",
  review_extraction_uncertain: "قيم اختلفت فيها القراءات",
  review_extracted_text: "النص المستخرج",
  review_extraction_errors: "{count} ملاحظة استخراج",
  detail_confirm_facts: "راجع الوقائع المالية ثم اضغط «تأكيد جميع الصفحات» للمتابعة.",
});

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
  user: "",                    // the Dataiku user signed in
  dash: { litigation: [], agreement_review: [], query: "", contractQuery: "", status: "", archived: false },
  reviewPageId: "",            // financial page shown beside the fact table
  pageExtractions: {},         // page_id -> stored extraction record (lazy)
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
  setPlaceholder("#library-search", "search_litigation_cases");
  setPlaceholder("#contract-search", "search_agreement_files");
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
    if (block === "---") { out.push('<hr class="bsf-divider">'); return; }
    const lines = block.split("\n");
    if (lines.every((line) => /^\s*\|/.test(line))) {
      const cells = (line) => line.trim().replace(/^\||\|$/g, "").split("|").map((cell) => cell.trim());
      const rows = lines.filter((line) => !/^\s*\|?\s*-{3,}/.test(line)).map(cells);
      const [head, ...rest] = rows;
      out.push(`<div class="bsf-table-scroll"><table class="bsf-table">
        <thead><tr>${head.map((cell) => `<th>${inline(cell)}</th>`).join("")}</tr></thead>
        <tbody>${rest.map((row) => `<tr>${row.map((cell) => `<td>${inline(cell)}</td>`).join("")}</tr>`).join("")}</tbody>
      </table></div>`);
      return;
    }
    if (lines.every((line) => /^\d+\.\s+/.test(line))) {
      out.push(`<ol>${lines.map((line) => `<li>${inline(line.replace(/^\d+\.\s+/, ""))}</li>`).join("")}</ol>`);
      return;
    }
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
  if (memo.format === "full_v2") { push(section); return chunks.filter(Boolean).join("\n\n"); }
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
          setTimeout(poll, 2000);
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
  const user = S.user || "";
  html(region("user-card"), user ? `
    <div class="bsf-user-avatar" aria-hidden="true">${esc(user.slice(0, 1).toUpperCase())}</div>
    <div>
      <div class="bsf-user-name">${esc(user)}</div>
      <div class="bsf-caption">${esc(t("signed_in_with_dataiku"))}</div>
    </div>` : "");

  const open = region("open-matter");
  if (S.snapshot) {
    show(open, true);
    region("chip-title").textContent = S.snapshot.display_name || t("open_matter");
    region("chip-ref").textContent = (S.snapshot.details || {}).case_number || S.snapshot.reference;
  } else {
    show(open, false);
  }
}

function progressLabel(key) {
  return key ? t(`progress_${key}`) : "";
}

const PROGRESS_KIND = {
  new: "neutral", documents_uploaded: "neutral", processing: "ai", accounting_review: "review",
  legal_analysis: "review", attorney_review: "provisional", ready_for_pleading: "verified", completed: "verified",
};

function friendlyStatus(status) {
  const key = String(status || "").trim().toLowerCase();
  const map = {
    intake: "status_intake", review: "status_review", analysis: "status_analysis",
    pleading: "status_pleading", final: "status_final",
  };
  return map[key] ? t(map[key]) : status;
}

/* ============================================================
   Dashboard: the signed-in user's own cases and contract reviews
   (the server only ever returns the user's own).
   ============================================================ */
function matchesQuery(item, query) {
  if (!query) return true;
  const haystack = [item.title, item.reference, item.matter, ...Object.values(item.details || {})]
    .join(" ").toLowerCase();
  return haystack.includes(query.toLowerCase());
}

function renderLibrary() {
  const dash = S.dash;
  region("dash-title").textContent = S.user ? t("dash_welcome", { user: S.user }) : t("dash_title");

  const litigation = dash.litigation.filter((item) => matchesQuery(item, dash.query)
    && (!dash.status || item.progress === dash.status));
  const contracts = dash.agreement_review.filter((item) => matchesQuery(item, dash.contractQuery));
  const attention = dash.litigation.filter((item) => ["accounting_review", "attorney_review"].includes(item.progress)).length;
  const metric = (value, key) => `<div class="bsf-metric"><span class="m-value">${esc(value)}</span>
    <span class="m-label">${esc(t(key))}</span></div>`;
  html(region("dash-metrics"), dash.archived ? "" : `
    ${metric(dash.litigation.length, "dash_metric_cases")}
    ${metric(attention, "dash_metric_attention")}
    ${metric(dash.litigation.filter((item) => item.progress === "completed").length, "dash_metric_completed")}
    ${metric(dash.agreement_review.length, "dash_metric_contracts")}`);

  const archiveButton = (item) => `<button type="button" class="bsf-btn bsf-btn-sm" data-action="archive-case"
      data-case-id="${esc(item.case_id)}" data-archived="${item.archived ? "0" : "1"}">
      ${esc(t(item.archived ? "restore_case" : "archive_case"))}</button>`;

  html(region("dash-litigation"), litigation.length ? `
    <div class="bsf-table-scroll"><table class="bsf-table bsf-dash-table">
      <thead><tr>
        <th>${esc(t("col_case_name"))}</th><th>${esc(t("col_case_number"))}</th><th>${esc(t("col_parties"))}</th>
        <th>${esc(t("col_case_type"))}</th><th>${esc(t("col_last_updated"))}</th><th>${esc(t("col_stage"))}</th><th></th>
      </tr></thead>
      <tbody>${litigation.map((item) => {
        const d = item.details || {};
        const parties = [d.client_name, d.opposing_party].filter(Boolean).join(" v ");
        return `<tr>
          <td dir="auto"><button type="button" class="bsf-link bsf-dash-open" data-action="open-case" data-case-id="${esc(item.case_id)}">
            ${esc(item.title || t("unnamed_case"))}</button></td>
          <td dir="auto">${esc(d.case_number || "—")}</td>
          <td dir="auto">${esc(parties || "—")}</td>
          <td dir="auto">${esc(d.case_type || item.matter || "—")}</td>
          <td>${esc(item.activity || "—")}</td>
          <td>${item.progress ? badge(progressLabel(item.progress), PROGRESS_KIND[item.progress] || "neutral") : "—"}</td>
          <td class="bsf-dash-actions">
            <button type="button" class="bsf-btn bsf-btn-sm bsf-btn-primary" data-action="open-case" data-case-id="${esc(item.case_id)}">
              ${esc(t(item.progress === "new" ? "open_case" : "continue_case"))}</button>
            ${archiveButton(item)}
          </td></tr>`;
      }).join("")}</tbody>
    </table></div>` : `<div class="bsf-empty">${esc(t(dash.archived ? "no_archived_cases" : "no_cases_yet"))}</div>`);

  html(region("dash-contracts"), contracts.length ? `
    <div class="bsf-table-scroll"><table class="bsf-table bsf-dash-table">
      <thead><tr>
        <th>${esc(t("col_contract_name"))}</th><th>${esc(t("col_contract_type"))}</th><th>${esc(t("col_counterparty"))}</th>
        <th>${esc(t("col_last_updated"))}</th><th>${esc(t("col_status"))}</th><th></th>
      </tr></thead>
      <tbody>${contracts.map((item) => {
        const d = item.details || {};
        return `<tr>
          <td dir="auto"><button type="button" class="bsf-link bsf-dash-open" data-action="open-case" data-case-id="${esc(item.case_id)}">
            ${esc(item.title || t("unnamed_agreement"))}</button></td>
          <td dir="auto">${esc(d.contract_type || item.matter || "—")}</td>
          <td dir="auto">${esc(d.counterparty || "—")}</td>
          <td>${esc(item.activity || "—")}</td>
          <td>${esc(friendlyStatus(item.status) || "—")}</td>
          <td class="bsf-dash-actions">
            <button type="button" class="bsf-btn bsf-btn-sm bsf-btn-primary" data-action="open-case" data-case-id="${esc(item.case_id)}">
              ${esc(t("continue_review"))}</button>
            ${archiveButton(item)}
          </td></tr>`;
      }).join("")}</tbody>
    </table></div>` : `<div class="bsf-empty">${esc(t(dash.archived ? "no_archived_contracts" : "no_contracts_yet"))}</div>`);
}

async function loadCases() {
  const archived = S.dash.archived ? "1" : "";
  try {
    const [litigation, contracts] = await Promise.all([
      apiGet("/cases", { workflow: "litigation", archived }),
      apiGet("/cases", { workflow: "agreement_review", archived }),
    ]);
    S.dash.litigation = litigation.cases || [];
    S.dash.agreement_review = contracts.cases || [];
  } catch (error) {
    S.dash.litigation = [];
    S.dash.agreement_review = [];
    fail(error);
  }
  S.cases = S.dash.litigation.concat(S.dash.agreement_review);
  renderSidebar();
  if (S.view === "library") renderLibrary();
}

/* New litigation case / contract review: the details are kept with the
   case and shown on the dashboard and in the case header. */
function openNewCaseForm(workflow) {
  const litigation = workflow !== "agreement_review";
  region("modal-title").textContent = t(litigation ? "new_litigation_case" : "new_contract_review");
  const field = (name, label, attrs = "") => `
    <label class="bsf-field"><span>${esc(t(label))}</span>
      <input type="text" class="bsf-input" name="${name}" dir="auto" ${attrs}></label>`;
  html(region("modal-body"), `
    <form data-form="create-case" data-workflow="${esc(workflow)}" class="bsf-new-case">
      ${field("case_name", litigation ? "col_case_name" : "col_contract_name", "required")}
      ${litigation ? `
        ${field("case_number", "field_case_number")}
        ${field("client_name", "field_client")}
        ${field("opposing_party", "field_opposing_party")}
        ${field("case_type", "col_case_type")}
        <label class="bsf-field"><span>${esc(t("field_description_optional"))}</span>
          <textarea class="bsf-input" name="description" rows="3" dir="auto"></textarea></label>` : `
        ${field("contract_type", "col_contract_type")}
        ${field("counterparty", "col_counterparty")}`}
      <label class="bsf-field"><span>${esc(t("preferred_language"))}</span>
        <select class="bsf-input" name="language"><option value="ar">العربية</option><option value="en">English</option></select></label>
      <button type="submit" class="bsf-btn bsf-btn-primary">${esc(t(litigation ? "create_case_and_upload" : "create_contract_review"))}</button>
    </form>`);
  setModalVisible(true);
  const first = $('[data-form="create-case"] input[name="case_name"]');
  if (first) first.focus();
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
    S.pleadingLang = null;
    S.accountingSelectedDocs = null;
    S.accountingKnownDocs = null;
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
  ready: "provisional", completed: "verified", stale: "review", error: "flagged", not_yet: "neutral",
};
/* What the user sees for a step: Done (finished, even if something
   changed after it) or Not yet; a running step keeps its progress bar. */
function shownStatus(stage) {
  const status = (stage && stage.status) || "";
  if (status === "running") return "running";
  return status === "completed" || status === "stale" ? "completed" : "not_yet";
}

const STAGE_ICONS = {
  completed: "\u2713", running: "\u21BB", waiting_for_user: "!", error: "\u2715",
  stale: "\u21BA", ready: "\u25CF", not_started: "\u25CB", blocked: "\u25CB", not_yet: "\u25CB",
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
  if (stage.status === "stale" || stage.status === "completed") return "";
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
    <div class="bsf-stage-strip status-${esc(shownStatus(stage))}">
      <div class="bsf-stage-strip-head">
        ${badge(t(`status_${shownStatus(stage)}`), STAGE_STATUS_KIND[shownStatus(stage)])}
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
      <span><strong>${esc(stageLabel(stage.key))}</strong> — ${esc(stageDetailText(stage) || t(`status_${shownStatus(stage)}`))}</span>
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
  const details = snap.details || {};
  html(region("case-meta"), [
    details.case_number ? `<span>${esc(t("field_case_number"))}: <strong dir="auto">${esc(details.case_number)}</strong></span>` : "",
    [details.client_name, details.opposing_party].filter(Boolean).length
      ? `<span dir="auto">${esc([details.client_name, details.opposing_party].filter(Boolean).join(" v "))}</span>` : "",
    snap.progress ? badge(progressLabel(snap.progress), PROGRESS_KIND[snap.progress] || "neutral") : "",
    snap.last_updated ? `<span class="bsf-caption">${esc(t("last_updated_at", { at: snap.last_updated }))}</span>` : "",
  ].filter(Boolean).join('<span class="bsf-meta-sep">|</span>'));

  // Finished steps stay shown as done, even when something changed after them.
  show(region("case-dirty"), false);

  renderAttention();
  renderStageStrips();
  renderCaseStatus();
  renderUnresolved();
  renderCaseSearch();
  renderDocumentsTab();
  renderDocumentsOverview();
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
  const done = stages.filter((stage) => shownStatus(stage) === "completed").length;
  const percent = stages.length ? Math.round((done / stages.length) * 100) : 0;

  const nextKey = snap.next_stage || "documents";
  const nextStage = stageByKey(nextKey) || { status: "" };
  let nextText;
  if (nextStage.status === "waiting_for_user") nextText = t("next_waiting", { stage: stageLabel(nextKey) });
  else if (nextStage.status === "error") nextText = t("next_error", { stage: stageLabel(nextKey) });
  else nextText = t(NEXT_ACTION_KEYS[nextKey] || "next_documents");
  const destination = t(STAGE_TAB_KEYS[nextKey] || "tab_documents");

  const stepCards = stages.map((stage) => `
    <button type="button" class="step-card ${shownStatus(stage) === "completed" ? "complete" : stage.state} status-${esc(shownStatus(stage))}"
            data-action="goto-stage" data-stage="${esc(stage.key)}">
      <div class="step-icon">${STAGE_ICONS[shownStatus(stage)] || ""}</div>
      <div class="step-label">${esc(stageLabel(stage.key))}</div>
      <div class="step-status">${esc(stage.status === "running" && stage.phase ? t(`phase_${stage.phase}`) : t(`status_${shownStatus(stage)}`))}</div>
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

/* Documents: what was uploaded and how each one was read. */
function renderDocumentsOverview() {
  const target = region("documents-overview");
  if (!target) return;
  const docs = (S.snapshot && S.snapshot.documents_overview) || [];
  if (!docs.length) { html(target, ""); return; }
  html(target, `
    <div class="bsf-table-scroll"><table class="bsf-table bsf-docs-table">
      <thead><tr>
        <th>${esc(t("col_file"))}</th><th>${esc(t("col_pages"))}</th><th>${esc(t("col_document_type"))}</th>
        <th>${esc(t("col_reading"))}</th><th>${esc(t("col_accounting"))}</th><th></th>
      </tr></thead>
      <tbody>${docs.map((doc) => {
        const reading = doc.pages_failed
          ? badge(t("doc_pages_failed", { count: doc.pages_failed }), "flagged")
          : doc.pages_to_check ? badge(t("doc_pages_to_check", { count: doc.pages_to_check }), "review")
          : badge(t("doc_read_ok"), "verified");
        const accounting = !doc.classified_pages ? `<span class="bsf-caption">${esc(t("doc_not_checked_yet"))}</span>`
          : doc.financial_pages ? badge(t("doc_financial_pages", { count: doc.financial_pages, facts: doc.facts }), "ai")
          : `<span class="bsf-caption">${esc(t("doc_no_financial_records"))}</span>`;
        return `<tr>
          <td dir="auto"><strong>${esc(doc.file)}</strong><div class="bsf-caption">${esc(doc.uploaded_at || "")}</div></td>
          <td>${esc(doc.pages)}</td>
          <td dir="auto">${esc((doc.document_types || []).join(", ") || doc.purpose || "—")}</td>
          <td>${reading}</td>
          <td>${accounting}</td>
          <td>${doc.first_page_id ? `<button type="button" class="bsf-btn bsf-btn-sm" data-action="view-page"
               data-page-id="${esc(doc.first_page_id)}">${esc(t("preview"))}</button>` : ""}</td>
        </tr>`;
      }).join("")}</tbody>
    </table></div>`);
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
  renderFactReview();
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
  // Documents uploaded since the list was first shown are selected too, so
  // a new PDF is never silently left out of the accounting.
  if (!S.accountingKnownDocs) S.accountingKnownDocs = new Set(S.accountingSelectedDocs);
  documents.forEach((doc) => {
    if (!S.accountingKnownDocs.has(doc.case_document_id)) {
      S.accountingKnownDocs.add(doc.case_document_id);
      S.accountingSelectedDocs.add(doc.case_document_id);
    }
  });

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

const FACT_AMOUNT_FIELDS = ["amount", "debit", "credit", "balance", "amount_due", "paid_amount", "remaining_amount"];
const FACT_STATUS_KIND = {
  EXTRACTED: "verified", CALCULATED: "ai", INFERRED: "provisional", UNCERTAIN: "review",
  MISSING: "neutral", USER_CONFIRMED: "verified", USER_CORRECTED: "provisional", IGNORED: "neutral",
};

function factTypeLabel(value) {
  if (!value) return "—";
  const key = `fact_type_${value}`;
  const text = t(key);
  return text !== key ? text : String(value).replace(/_/g, " ");
}

function factStatusBadge(status) {
  return badge(t(`fact_status_${status}`), FACT_STATUS_KIND[status] || "neutral");
}

/* ============================================================
   Financial fact review: the page beside the table of atomic facts.
   The rows of the page on screen are highlighted; Previous / Next move
   to the next financial page and the highlight follows. Cells are
   edited in place (click, type, Enter); every edit is saved at once,
   layered on the AI's reading, which stays visible. Uncertain values
   are marked in the table. "Confirm all pages" unlocks the accounting
   analysis.
   ============================================================ */
const FACT_TYPE_OPTIONS = [
  "transaction", "payment", "installment", "deposit", "withdrawal", "transfer", "financing_amount",
  "outstanding_balance", "remaining_balance", "amount_due", "opening_balance", "closing_balance", "balance",
  "fee", "interest", "penalty", "credit_limit", "claimed_amount", "other",
];
const REVIEW_COLUMNS = ["date", "fact_type", "description", "amount", "debit", "credit", "balance", "currency"];
const REVIEW_ALWAYS = ["date", "fact_type", "description", "amount"];

/* Columns with a value somewhere in the table (date, type, description
   and amount are always shown, so they can be filled in). */
function reviewColumns(facts) {
  return REVIEW_COLUMNS.filter((name) => REVIEW_ALWAYS.includes(name)
    || facts.some((fact) => fact[name] !== null && fact[name] !== undefined && fact[name] !== ""));
}

function reviewState() {
  const acc = (S.snapshot && S.snapshot.accounting) || {};
  const pages = acc.financial_pages || [];
  const facts = acc.facts_table || [];
  // Pages that only have facts (e.g. classified before) still appear.
  const known = new Set(pages.map((page) => page.page_id));
  facts.forEach((fact) => {
    if (fact.page_id && !known.has(fact.page_id)) {
      known.add(fact.page_id);
      pages.push({ page_id: fact.page_id, page_number: fact.page_number, document_name: fact.document_name || "",
                   label: "", image_url: `/page_image?case_id=${S.caseId}&page_id=${fact.page_id}` });
    }
  });
  return { acc, pages, facts };
}

function rememberedReviewPage() {
  try { return window.localStorage.getItem(`bsf-review-page-${S.caseId}`) || ""; } catch (error) { return ""; }
}

function rememberReviewPage(pageId) {
  try { window.localStorage.setItem(`bsf-review-page-${S.caseId}`, pageId); } catch (error) { /* private mode */ }
}

function currentReviewPage(pages) {
  if (!pages.length) return null;
  const wanted = S.reviewPageId || rememberedReviewPage();
  return pages.find((page) => page.page_id === wanted) || pages[0];
}

function reviewPageTitle(page) {
  return page.label || `${page.document_name || ""} — ${t("page_label")} ${page.page_number || "—"}`;
}

function factCell(fact, name, editable) {
  const raw = fact[name];
  const shown = name === "fact_type" ? factTypeLabel(raw) : (raw === null || raw === undefined || raw === "" ? "—" : raw);
  const original = (fact.original_values || {})[name];
  const edited = Object.prototype.hasOwnProperty.call(fact.original_values || {}, name);
  const title = edited
    ? t("review_cell_edited", { value: original === null || original === undefined || original === "" ? "—" : original,
                                 by: fact.edited_by || t("review_you") })
    : (editable ? t("review_cell_click_to_edit") : "");
  return `<td dir="auto" class="bsf-fr-cell${edited ? " is-edited" : ""}${FACT_AMOUNT_FIELDS.includes(name) ? " is-number" : ""}"
             ${editable ? `data-action="edit-fact-cell" data-row-id="${esc(fact.row_id)}" data-field="${esc(name)}"` : ""}
             title="${esc(title)}">${esc(shown)}${edited ? '<span class="bsf-fr-edited-mark" aria-hidden="true">✎</span>' : ""}</td>`;
}

function factRowMarkup(fact, currentPageId, columns) {
  const current = fact.page_id === currentPageId;
  const uncertain = fact.status === "UNCERTAIN";
  const review = fact.review || {};
  const reason = [review.question, review.reason].filter(Boolean).join(" — ");
  const classes = ["bsf-fr-row", current ? "is-current" : "is-other", uncertain ? "is-uncertain" : "",
                   fact.deleted ? "is-deleted" : ""].filter(Boolean).join(" ");
  const source = fact.added_by_user ? badge(t("review_added_by_you"), "provisional")
    : (fact.corrected_fields || []).length ? badge(t("review_edited_by_you"), "provisional")
    : fact.status === "USER_CONFIRMED" ? badge(t("review_confirmed"), "verified")
    : uncertain ? badge(t("fact_status_UNCERTAIN"), "review")
    : badge(t("review_from_ai"), "ai");
  const editable = !fact.deleted;
  return `
    <tr class="${classes}" data-page-id="${esc(fact.page_id)}" data-row-id="${esc(fact.row_id)}">
      <td class="bsf-fr-page-cell"><button type="button" class="bsf-link" data-action="review-goto-page"
          data-page-id="${esc(fact.page_id)}">${esc(fact.page_number || "—")}</button></td>
      ${columns.map((name) => factCell(fact, name, editable)).join("")}
      <td class="bsf-fr-status">${source}
        ${fact.source_type ? `<div class="bsf-caption">${esc(t("review_source_type", { type: String(fact.source_type).replace(/_/g, " ") }))}</div>` : ""}
        ${uncertain && reason ? `<div class="bsf-fr-reason">${esc(reason)}</div>` : ""}
        ${(review.alternatives || []).length && uncertain
          ? `<div class="bsf-fr-reason">${esc(t("fact_alternatives"))}: ${esc(review.alternatives.join(" / "))}</div>` : ""}
        ${fact.supporting_table || fact.source_text ? `<details class="bsf-fr-source"><summary>${esc(t("review_as_printed"))}</summary>
          <div dir="auto">${fact.supporting_table ? renderExtractionMarkdown(fact.supporting_table) : `<pre>${esc(fact.source_text)}</pre>`}</div>
        </details>` : ""}
      </td>
      <td class="bsf-fr-actions">${fact.deleted
        ? `<button type="button" class="bsf-btn bsf-btn-sm" data-action="restore-fact" data-row-id="${esc(fact.row_id)}">${esc(t("review_restore"))}</button>`
        : `<button type="button" class="bsf-btn bsf-btn-sm" data-action="delete-fact" data-row-id="${esc(fact.row_id)}"
             title="${esc(t("review_delete_title"))}">✕</button>`}</td>
    </tr>`;
}

function renderExtractionMarkdown(text) {
  // Wrapped cell text is joined with <br> by the extraction.
  return renderMarkdown(String(text || "")).replace(/&lt;br\s*\/?&gt;/gi, "<br>");
}

function addFactFormMarkup(page) {
  return `
    <details class="bsf-fr-add" ${S.reviewAddOpen ? "open" : ""}>
      <summary class="bsf-btn bsf-btn-sm">${esc(t("review_add_fact", { page: page.page_number || "—" }))}</summary>
      <form class="bsf-fr-add-form" data-form="add-fact" data-page-id="${esc(page.page_id)}">
        <label class="bsf-field"><span>${esc(t("field_date"))}</span><input class="bsf-input" name="date" dir="auto"></label>
        <label class="bsf-field"><span>${esc(t("column_fact_type"))}</span>
          <select class="bsf-input" name="fact_type">${FACT_TYPE_OPTIONS.map((type) =>
            `<option value="${type}" ${type === "transaction" ? "selected" : ""}>${esc(factTypeLabel(type))}</option>`).join("")}</select></label>
        <label class="bsf-field bsf-fr-wide"><span>${esc(t("field_description"))}</span><input class="bsf-input" name="description" dir="auto"></label>
        <label class="bsf-field"><span>${esc(t("field_amount"))}</span><input class="bsf-input" name="amount" inputmode="decimal"></label>
        <label class="bsf-field"><span>${esc(t("column_balance"))}</span><input class="bsf-input" name="balance" inputmode="decimal"></label>
        <label class="bsf-field"><span>${esc(t("column_currency"))}</span><input class="bsf-input" name="currency"></label>
        <button type="submit" class="bsf-btn bsf-btn-primary">${esc(t("review_add_save"))}</button>
      </form>
    </details>`;
}

function renderFactReview() {
  const target = region("accounting-review");
  if (!target) return;
  const { acc, pages, facts } = reviewState();
  if (!facts.length && !pages.length) {
    html(target, `<p class="bsf-caption">${esc(t("no_line_items"))}</p>`);
    return;
  }
  const page = currentReviewPage(pages);
  const index = page ? pages.findIndex((item) => item.page_id === page.page_id) : -1;
  const pageFacts = facts.filter((fact) => page && fact.page_id === page.page_id);
  const uncertain = facts.filter((fact) => fact.status === "UNCERTAIN" && !fact.deleted).length;
  const confirmed = Boolean(acc.facts_confirmed);
  const columns = reviewColumns(facts);

  html(target, `
    <h4 class="bsf-subsection">${esc(t("review_heading"))}</h4>
    <p class="bsf-caption">${esc(t("review_caption"))}</p>
    ${confirmed
      ? alertBox(t("review_confirmed_by", { by: acc.facts_confirmed_by || "—", at: String(acc.facts_confirmed_at || "").slice(0, 16).replace("T", " ") }), "ok")
      : uncertain ? alertBox(t("review_uncertain_count", { count: uncertain }), "warn") : ""}
    <div class="bsf-fr">
      <div class="bsf-fr-pane">
        ${page ? `
          <div class="bsf-fr-pane-title" dir="auto">${esc(reviewPageTitle(page))}
            <span class="bsf-caption">${esc(t("review_page_position", { index: index + 1, total: pages.length }))}</span></div>
          <button type="button" class="bsf-fr-image" data-action="view-page" data-page-id="${esc(page.page_id)}"
                  title="${esc(t("review_open_full_page"))}">
            <img src="${esc(backendUrl(page.image_url))}" alt="${esc(reviewPageTitle(page))}">
          </button>
          <details class="bsf-expander bsf-fr-extraction" data-page-id="${esc(page.page_id)}">
            <summary>${esc(t("review_extraction_heading", { page: page.page_number || "—" }))}</summary>
            <div class="bsf-expander-body" data-region="review-extraction"></div>
          </details>` : ""}
      </div>
      <div class="bsf-fr-table-wrap">
        ${page && !pageFacts.length ? alertBox(t("review_no_facts_on_page"), "info") : ""}
        <div class="bsf-fr-table-scroll" data-region="review-table-scroll">
          <table class="bsf-table bsf-fr-table">
            <thead><tr>
              <th>${esc(t("column_page"))}</th>
              ${columns.map((name) => `<th>${esc(t(name === "fact_type" ? "column_fact_type"
                : name === "date" ? "column_fin_date" : name === "description" ? "column_description"
                : name === "amount" ? "field_amount" : `column_${name}`))}</th>`).join("")}
              <th>${esc(t("column_row_status"))}</th><th></th>
            </tr></thead>
            <tbody>${facts.map((fact) => factRowMarkup(fact, page ? page.page_id : "", columns)).join("")}</tbody>
          </table>
        </div>
        ${page ? addFactFormMarkup(page) : ""}
      </div>
    </div>
    <div class="bsf-fr-nav">
      <button type="button" class="bsf-btn" data-action="review-step" data-step="-1" ${index <= 0 ? "disabled" : ""}>
        ${esc(isRTL() ? "▶" : "◀")} ${esc(t("review_previous_page"))}</button>
      <select class="bsf-input bsf-fr-page-select" data-action="review-select-page" aria-label="${esc(t("page_label"))}">
        ${pages.map((item, i) => `<option value="${esc(item.page_id)}" ${page && item.page_id === page.page_id ? "selected" : ""}>
          ${esc(`${i + 1}. ${reviewPageTitle(item)} (${facts.filter((f) => f.page_id === item.page_id && !f.deleted).length})`)}</option>`).join("")}
      </select>
      <button type="button" class="bsf-btn" data-action="review-step" data-step="1" ${index >= pages.length - 1 ? "disabled" : ""}>
        ${esc(t("review_next_page"))} ${esc(isRTL() ? "◀" : "▶")}</button>
      <span class="bsf-fr-spacer"></span>
      <button type="button" class="bsf-btn bsf-btn-primary" data-action="confirm-all-facts" ${facts.length ? "" : "disabled"}>
        ${esc(confirmed ? t("review_confirm_again") : t("review_confirm_all"))}</button>
    </div>
    ${documentClaimsMarkup(acc.document_claims || [], page ? page.page_id : "")}`);

  scrollToCurrentRows();
  const extraction = target.querySelector(".bsf-fr-extraction");
  if (extraction) {
    if (S.reviewExtractionOpen) extraction.open = true;
    extraction.addEventListener("toggle", () => {
      S.reviewExtractionOpen = extraction.open;
      if (extraction.open) loadPageExtraction(extraction.dataset.pageId);
    });
    if (extraction.open) loadPageExtraction(extraction.dataset.pageId);
  }
  const addForm = target.querySelector(".bsf-fr-add");
  if (addForm) addForm.addEventListener("toggle", () => { S.reviewAddOpen = addForm.open; });
  const synthesize = document.querySelector('[data-action="accounting-synthesize"]');
  if (synthesize) synthesize.disabled = !confirmed;
}

/* Layer 1: what the documents SAY about money (emails, narrative sections).
   Shown apart from the facts: the accountant verifies them against the
   records; they are never part of the ledger. */
function documentClaimsMarkup(claims, currentPageId) {
  if (!claims.length) return "";
  return `
    <details class="bsf-expander bsf-fr-claims">
      <summary>${esc(t("review_claims_heading", { count: claims.length }))}</summary>
      <div class="bsf-expander-body">
        <p class="bsf-caption">${esc(t("review_claims_caption"))}</p>
        <table class="bsf-table">
          <thead><tr><th>${esc(t("column_page"))}</th><th>${esc(t("review_claim_statement"))}</th>
            <th>${esc(t("review_claim_by"))}</th><th>${esc(t("review_claim_amounts"))}</th></tr></thead>
          <tbody>${claims.map((claim) => `
            <tr class="${claim.page_id === currentPageId ? "is-current-claim" : ""}">
              <td><button type="button" class="bsf-link" data-action="review-goto-page" data-page-id="${esc(claim.page_id)}">
                ${esc(claim.page_label || claim.page_number || "—")}</button></td>
              <td dir="auto">${esc(claim.statement)}</td>
              <td dir="auto">${esc(claim.made_by || "—")}</td>
              <td dir="auto">${esc((claim.amounts || []).join(", ") || "—")}</td>
            </tr>`).join("")}</tbody>
        </table>
      </div>
    </details>`;
}

function scrollToCurrentRows() {
  const box = region("review-table-scroll");
  if (!box) return;
  const first = box.querySelector("tr.is-current");
  if (!first) return;
  const head = box.querySelector("thead");
  box.scrollTop = Math.max(0, first.offsetTop - (head ? head.offsetHeight : 0) - 4);
}

async function loadPageExtraction(pageId) {
  const target = region("review-extraction");
  if (!target || !pageId) return;
  S.pageExtractions = S.pageExtractions || {};
  let record = S.pageExtractions[pageId];
  if (!record) {
    html(target, `<p class="bsf-caption">${esc(t("loading"))}</p>`);
    try {
      record = await apiGet("/accounting/page_extraction", { case_id: S.caseId, page_id: pageId });
      S.pageExtractions[pageId] = record;
    } catch (error) {
      html(target, alertBox(t("request_failed", { error: error.message }), "flag"));
      return;
    }
  }
  if (region("review-extraction") !== target) return;
  const routeKey = { native: "review_route_native", "native+vlm": "review_route_mixed", vlm: "review_route_vlm" }[record.route];
  html(target, `
    <div class="bsf-fr-meta">
      ${routeKey ? badge(t(routeKey), "neutral") : ""}
      ${(record.regions || []).map((r) => badge(`${t(`review_kind_${r.kind}`)}${(r.flags || []).length
        ? " · " + r.flags.map((flag) => t(`review_flag_${flag}`)).join(", ") : ""}`, "neutral")).join(" ")}
      ${(record.candidates || []).length ? `<span class="bsf-caption">${esc(t("review_candidates", { names: record.candidates.join(", ") }))}</span>` : ""}
    </div>
    ${record.note ? `<p class="bsf-caption">${esc(record.note)}</p>` : ""}
    ${(record.uncertain || []).length ? `
      <div class="bsf-review-label">${esc(t("review_extraction_uncertain"))}</div>
      <ul class="bsf-fr-uncertain">${record.uncertain.map((u) => `<li dir="auto"><strong>${esc(u.value || "")}</strong>
        ${(u.readings || []).length ? ` — ${esc(u.readings.join(" | "))}` : ""}${u.reason ? ` <span class="bsf-caption">(${esc(u.reason)})</span>` : ""}</li>`).join("")}</ul>` : ""}
    <div class="bsf-review-label">${esc(t("review_extracted_text"))}</div>
    <div class="bsf-fr-text" dir="auto">${renderExtractionMarkdown(record.final_text || "")}</div>
    ${(record.errors || []).length ? `<details><summary class="bsf-caption">${esc(t("review_extraction_errors", { count: record.errors.length }))}</summary>
      <pre>${esc(record.errors.join("\n"))}</pre></details>` : ""}`);
}

function goToReviewPage(pageId) {
  if (!pageId) return;
  S.reviewPageId = pageId;
  rememberReviewPage(pageId);
  renderFactReview();
}

/* Edits are saved one at a time, in order; the table is updated from the
   server's answer, the stage strip after the user pauses. */
let factSaveQueue = Promise.resolve();
let reviewRefreshTimer = null;

function scheduleReviewRefresh() {
  clearTimeout(reviewRefreshTimer);
  reviewRefreshTimer = setTimeout(() => refreshCase(), 1500);
}

function saveFactChange(path, body) {
  factSaveQueue = factSaveQueue.then(async () => {
    try {
      const saved = await apiPost(path, Object.assign({ case_id: S.caseId }, body));
      if (saved.facts_table && S.snapshot && S.snapshot.accounting) {
        S.snapshot.accounting.facts_table = saved.facts_table;
        if (typeof saved.facts_confirmed === "boolean") S.snapshot.accounting.facts_confirmed = saved.facts_confirmed;
      }
      renderFactReview();
      scheduleReviewRefresh();
      return saved;
    } catch (error) {
      fail(error);
      renderFactReview();
      return null;
    }
  });
  return factSaveQueue;
}

function startCellEdit(cell) {
  if (cell.querySelector("input, select")) return;
  const rowId = cell.dataset.rowId;
  const field = cell.dataset.field;
  const fact = (reviewState().facts || []).find((item) => item.row_id === rowId);
  if (!fact) return;
  const value = fact[field] === null || fact[field] === undefined ? "" : String(fact[field]);
  const control = field === "fact_type"
    ? Object.assign(document.createElement("select"), {
        innerHTML: FACT_TYPE_OPTIONS.map((type) => `<option value="${type}" ${type === value ? "selected" : ""}>${esc(factTypeLabel(type))}</option>`).join(""),
      })
    : Object.assign(document.createElement("input"), { value, dir: "auto" });
  control.className = "bsf-input bsf-fr-input";
  if (FACT_AMOUNT_FIELDS.includes(field)) control.inputMode = "decimal";
  cell.textContent = "";
  cell.appendChild(control);
  control.focus();
  if (control.select) control.select();

  let done = false;
  const finish = (save) => {
    if (done) return;
    done = true;
    const next = control.value.trim();
    if (!save || next === value) { renderFactReview(); return; }
    cell.classList.add("is-saving");
    saveFactChange("/accounting/fact/update", { row_id: rowId, fields: { [field]: next } });
  };
  control.addEventListener("keydown", (event) => {
    if (event.key === "Enter") { event.preventDefault(); finish(true); }
    else if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); finish(false); }
  });
  control.addEventListener("blur", () => finish(true));
  if (field === "fact_type") control.addEventListener("change", () => finish(true));
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
        <th>${esc(t("column_fin_date"))}</th><th>${esc(t("column_fact_type"))}</th>
        <th>${esc(t("column_description"))}</th><th>${esc(t("column_value"))}</th>
        <th>${esc(t("column_row_status"))}</th><th>${esc(t("column_page"))}</th>
      </tr></thead>
      <tbody>${rows.map((row) => `<tr>
        <td>${esc(row.date || "—")}</td><td>${esc(factTypeLabel(row.fact_type))}</td>
        <td>${esc(row.description || "")}</td>
        <td>${esc(row.value || "—")} ${esc(row.currency || "")}</td>
        <td>${row.status ? factStatusBadge(row.status) : ""}</td>
        <td>${row.page_id ? sourceLinks([row.page_id], [row.page_label || t("source_page")]) : ""}</td>
      </tr>`).join("")}</tbody>
    </table>` : "";

  const block = (label, body, kind) => `
    <div class="bsf-claim-block${kind ? ` is-${kind}` : ""}">
      <div class="bsf-review-label">${esc(label)}</div>
      ${body}
    </div>`;

  const group = (item, key, kind) => {
    const entries = item[key] || [];
    if (!entries.length) return "";
    return block(t(`${key}_label`), entries.map((entry) => `
      <div class="bsf-claim-evidence">
        ${entry.explanation ? `<div>${esc(entry.explanation)}</div>` : ""}
        ${rowsTable(entry.rows || [])}
      </div>`).join(""), kind);
  };

  const amounts = (item) => {
    const parts = [];
    if (item.claimed_amount) parts.push(`<span><strong>${esc(t("claimed_amount_label"))}:</strong> ${esc(item.claimed_amount)} ${esc(item.currency || "")}</span>`);
    if (item.substantiated_amount) parts.push(`<span><strong>${esc(t("substantiated_amount_label"))}:</strong> ${esc(item.substantiated_amount)} ${esc(item.currency || "")}</span>`);
    const totals = item.evidence_totals || {};
    const totalText = Object.keys(totals).map((currency) => `${totals[currency]} ${currency === "—" ? "" : currency}`).join(" · ");
    if (totalText) parts.push(`<span><strong>${esc(t("evidence_total_label"))}:</strong> ${esc(totalText)}</span>`);
    return parts.length ? `<div class="bsf-claim-amounts">${parts.join("")}</div>` : "";
  };

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
          ${item.parent_claim && item.parent_claim !== item.claim
            ? `<p class="bsf-caption">${esc(t("claim_parent", { text: item.parent_claim }))}</p>` : ""}
          ${amounts(item)}
          ${item.accounting_position ? `
            <div class="bsf-claim-position">
              <div class="bsf-review-label">${esc(t("accounting_position_label"))}</div>
              <div>${esc(item.accounting_position)}</div>
            </div>` : ""}
          ${item.financial_question ? `<div class="bsf-kv"><strong>${esc(t("financial_question_label"))}:</strong> ${esc(item.financial_question)}</div>` : ""}
          ${item.expected_evidence ? block(t("expected_evidence_label"), `<div>${esc(item.expected_evidence)}</div>`) : ""}
          ${group(item, "supporting_evidence", "support")}
          ${group(item, "partially_supporting_evidence", "partial")}
          ${group(item, "contradicting_evidence", "contra")}
          ${group(item, "unresolved_evidence", "unresolved")}
          ${block(t("missing_evidence_label"), (item.missing_evidence || []).length
            ? `<ul class="bsf-claim-list">${item.missing_evidence.map((text) => `<li>${esc(text)}</li>`).join("")}</ul>`
            : `<p class="bsf-caption">${esc(t("none_identified"))}</p>`)}
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
      ${analysisIssuesMarkup(analysis.issues || [])}

      <div class="bsf-btn-row">
        <button type="button" class="bsf-btn bsf-btn-primary" data-action="goto-stage" data-stage="pleading">
          ${esc(t("continue_to_written_pleading"))}</button>
      </div>`);
  }
}

/* Issues backed by at least one retrieved authority node are shown in
   full; the others are listed together, stating that no knowledge-base
   text supports them. */
function issueHasAuthority(item) {
  if (item && Object.prototype.hasOwnProperty.call(item, "has_authority")) return Boolean(item.has_authority);
  return (item.applicable_rules || []).some((rule) => (rule.node_ids || []).length);
}

function analysisIssuesMarkup(issues) {
  const failed = issues.filter((item) => item && item.analysis_failed);
  const analysed = issues.filter((item) => !(item && item.analysis_failed));
  const supported = analysed.filter(issueHasAuthority);
  const unsupported = analysed.filter((item) => !issueHasAuthority(item));
  return `
    ${supported.map((item) => `
      <div class="bsf-issue">
        <h4>${esc(item.issue_title || "")}</h4>
        <div class="bsf-kv"><strong>${esc(t("kb_rules"))}</strong></div>
        <ul>${item.applicable_rules.filter((rule) => (rule.node_ids || []).length).map((rule) => `
          <li>${esc(rule.proposition || "")} <code>[${esc((rule.node_ids || []).join(", "))}]</code></li>`).join("")}</ul>
        <div class="bsf-kv"><strong>${esc(t("our_position"))}</strong> ${esc(item.our_position || "")}</div>
        <div class="bsf-kv"><strong>${esc(t("opponent_position"))}</strong> ${esc(item.opponent_position || "")}</div>
        <div class="bsf-kv"><strong>${esc(t("response_label"))}</strong> ${esc(item.response || "")}</div>
        <div class="bsf-kv"><strong>${esc(t("conclusion_label"))}</strong> ${conclusionBadge(item.conclusion)}</div>
        <div class="bsf-kv"><strong>${esc(t("residual_risk_label"))}</strong> ${esc(item.residual_risk || "")}</div>
      </div>`).join("")}
    ${!supported.length ? alertBox(t("no_issue_with_authority"), "info") : ""}
    ${unsupported.length ? `
      <div class="bsf-issue bsf-issue-unsupported">
        <h4>${esc(t("issues_without_authority", { count: unsupported.length }))}</h4>
        <p class="bsf-caption">${esc(t("issues_without_authority_note"))}</p>
        <ul>${unsupported.map((item) => `<li>${esc(item.issue_title || "")}</li>`).join("")}</ul>
      </div>` : ""}
    ${failed.length ? `
      <div class="bsf-issue bsf-issue-unsupported">
        <h4>${esc(t("issues_not_analysed", { count: failed.length }))}</h4>
        <p class="bsf-caption">${esc(t("issues_not_analysed_note"))}</p>
        <ul>${failed.map((item) => `<li>${esc(item.issue_title || "")}</li>`).join("")}</ul>
      </div>` : ""}`;
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

// The pleading is drafted from the legal analysis and the accounting
// analysis (the backend checks the attorney-review gate as configured).
const canDraft = legalAnalysisReady && accountingReady;

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

  const reason = !legalAnalysisReady ? t("block_no_legal_analysis") : t("block_accounting_incomplete");

  html(
    locked,
    `<p class="bsf-caption">${esc(
      t("locked_reason", { reason })
    )}</p>`
  );
}

  const languageSelect = $("#pleading-language");
  if (languageSelect) languageSelect.value = preferredPleadingLanguage();

  const body = region("pleading-body");
  if (!memo) { html(body, ""); return; }

  // The pleading is drafted in one language, chosen before generating.
  const lang = pleadingLanguage(memo);
  const langs = [lang];

  html(body, `
    <div class="bsf-btn-row">
      ${langs.map((l) => `<button type="button" class="bsf-btn" data-action="download" data-fmt="md" data-lang="${l}">
        ${esc(t(l === "ar" ? "download_arabic_pleading" : "download_english_pleading"))}</button>`).join("")}
      <button type="button" class="bsf-btn" data-action="download" data-fmt="docx" data-lang="${lang}">
        ${esc(t("download_pleading_docx"))}</button>
    </div>

    ${langs.map((l) => `
    ${langs.length > 1 ? `<h3 class="bsf-section-title">${esc(l === "ar" ? "النسخة العربية" : "English version")}</h3>` : ""}
    <div class="bsf-pleading-body ${l === "ar" ? "arabic-block" : "english-block"}"
         dir="${l === "ar" ? "rtl" : "ltr"}" lang="${l}"
         data-region="pleading-markdown-${l}">${esc(t("loading"))}</div>`).join("")}

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

  langs.forEach((l) => loadPleadingMarkdown(l));
}

async function loadPleadingMarkdown(lang) {
  const target = region(`pleading-markdown-${lang}`);
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

/* Language a stored pleading was drafted in (older pleadings held both
   languages and follow the interface language). */
function pleadingLanguage(memo) {
  if (memo && (memo.language === "ar" || memo.language === "en")) return memo.language;
  if (memo && memo.pleading_en && memo.pleading_ar) return S.lang;
  return memo && memo.pleading_ar && !memo.pleading_en ? "ar" : "en";
}

/* Language the next pleading is drafted in: the one picked on the tab
   (saved with the case), else the case's preferred language. */
function preferredPleadingLanguage() {
  const state = (S.snapshot && S.snapshot.workflow_state) || {};
  const preferred = String(((S.snapshot && S.snapshot.case) || {}).preferred_language || "").toLowerCase();
  if (S.pleadingLang) return S.pleadingLang;
  if (state.pleading_language === "ar" || state.pleading_language === "en") return state.pleading_language;
  if (preferred === "ar" || preferred === "en") return preferred;
  return state.memo ? pleadingLanguage(state.memo) : S.lang;
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
            <div class="bsf-diff ${pleadingLanguage(current.draft) === "ar" ? "arabic-block" : "english-block"}">
              ${renderDiff(memoPlainText(chosen.draft, pleadingLanguage(current.draft)), memoPlainText(current.draft, pleadingLanguage(current.draft)))}
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
    ${contractDocumentMarkup(state)}

    <details class="bsf-review-details">
    <summary>${esc(t("review_details"))}</summary>
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
    ${negotiationMarkup(negotiation)}
    </details>`);
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
      ${(item.edits || []).length ? `
        <div class="bsf-kv"><strong>${esc(t("proposed_changes"))}</strong></div>
        <ul class="bsf-mk-list">${item.edits.map((edit) => `<li>${editMarkup(edit)}</li>`).join("")}</ul>` : `
      ${change ? `<div class="bsf-kv"><strong>${esc(t("recommended_action"))}</strong> ${esc(change)}</div>` : ""}
      ${wording ? `<div class="bilingual-panel ${ar ? "arabic-block" : "english-block"}">${esc(wording)}</div>` : ""}`}
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

/* One wording change: the words to change in red, an arrow, and how they
   should read in green (delete: struck out; add: the new words only). */
const ARABIC_RE = /[\u0600-\u06FF]/;

function editArrow(text) { return ARABIC_RE.test(text || "") ? "\u2190" : "\u2192"; }

function editReason(edit) {
  return (isRTL() ? (edit.reason_ar || edit.reason_en) : (edit.reason_en || edit.reason_ar)) || "";
}

function editNew(edit) {
  const arrow = editArrow(edit.original || edit.replacement);
  if (edit.type === "delete") {
    return `<span class="bsf-mk-arrow">${arrow}</span><span class="bsf-mk-del">${esc(t("marked_delete"))}</span>`;
  }
  return `<span class="bsf-mk-arrow">${arrow}</span><span class="bsf-mk-new">${edit.type === "add" ? "+ " : ""}${esc(edit.replacement || "")}</span>`;
}

function editMarkup(edit) {
  const old = edit.type === "add" ? "" : `<span class="bsf-mk-old${edit.type === "delete" ? " is-deleted" : ""}">${esc(edit.original || "")}</span>`;
  const reason = editReason(edit);
  return `<span class="bsf-mk" dir="auto" title="${esc(reason)}">${old}${editNew(edit)}</span>
    ${reason ? `<div class="bsf-caption">${esc(reason)}</div>` : ""}`;
}

/* The contract as one document (agreement_markup.contract_document):
   headings, paragraphs, lists and tables from the extracted text, each
   proposed change in place - the wording to change in red, struck
   through, the proposed wording in green right after it. */
function contractDocumentMarkup(state) {
  const contract = state.contract;
  if (!contract || !(contract.blocks || []).length) return "";
  const edits = contract.edits || {};
  const change = (edit, inner) => `<span class="bsf-ct-change" title="${esc(editReason(edit))}">${inner}</span>`;
  const proposed = (edit) => edit.type === "delete" ? ""
    : `<ins class="bsf-ct-new">${esc(edit.replacement || "")}</ins>`;
  const run = (item) => {
    const edit = edits[item.edit_id];
    if (item.kind === "text" || !edit) return esc(item.text || "");
    if (item.kind === "insert") return " " + change(edit, proposed(edit));
    const old = `<del class="bsf-ct-old">${esc(item.text || "")}</del>`;
    return change(edit, item.last && edit.type !== "delete" ? `${old} ${proposed(edit)}` : old);
  };
  const runs = (list) => (list || []).map(run).join("");
  const table = (block) => `
    <div class="bsf-table-scroll"><table class="bsf-table bsf-ct-table">${(block.rows || []).map((row) => `
      <tr>${(row.cells || []).map((cell) => row.header
        ? `<th dir="auto">${runs(cell)}</th>` : `<td dir="auto">${runs(cell)}</td>`).join("")}</tr>`).join("")}
    </table></div>`;

  const parts = [];
  let items = [];
  const flush = () => { if (items.length) { parts.push(`<ul class="bsf-ct-list">${items.join("")}</ul>`); items = []; } };
  (contract.blocks || []).forEach((block) => {
    if (block.type === "item") { items.push(`<li dir="auto">${runs(block.runs)}</li>`); return; }
    flush();
    if (block.type === "document") parts.push(`<h2 class="bsf-ct-file">${esc(block.text || "")}</h2>`);
    else if (block.type === "page") parts.push(`<div class="bsf-ct-page"><span>${esc(t("contract_page", { page: block.page_number }))}</span></div>`);
    else if (block.type === "heading") {
      const tag = block.level === 1 ? "h2" : (block.level === 2 ? "h3" : "h4");
      parts.push(`<${tag} class="bsf-ct-h${block.level || 2}" dir="auto">${runs(block.runs)}</${tag}>`);
    } else if (block.type === "table") parts.push(table(block));
    else parts.push(`<p dir="auto">${runs(block.runs)}</p>`);
  });
  flush();

  const sample = (contract.blocks || []).slice(0, 40).map((b) => (b.runs || []).map((r) => r.text || "").join("")).join(" ");
  const direction = ARABIC_RE.test(sample) && (sample.match(/[؀-ۿ]/g) || []).length * 2
    >= (sample.match(/[A-Za-z؀-ۿ]/g) || []).length ? "rtl" : "ltr";
  const unplaced = (contract.unplaced || []).map((id) => edits[id]).filter(Boolean);
  return `
    <div class="bsf-ct-bar">
      <div>
        <h4 class="bsf-subsection">${esc(t("contract_with_changes"))}</h4>
        <p class="bsf-caption">${esc(t("contract_changes_caption", { count: contract.changes || 0 }))}
          <span class="bsf-ct-legend"><del class="bsf-ct-old">${esc(t("contract_legend_old"))}</del>
          <ins class="bsf-ct-new">${esc(t("contract_legend_new"))}</ins></span></p>
      </div>
      <div class="bsf-ct-actions">
        <button type="button" class="bsf-btn bsf-btn-primary" data-action="download-contract-docx">${esc(t("download_contract_docx"))}</button>
        <div class="bsf-caption">${esc(t("contract_docx_note"))}</div>
      </div>
    </div>
    ${state.has_edits ? "" : alertBox(t("contract_no_edits"), "info")}
    <article class="bsf-ct-paper" dir="${direction}">${parts.join("")}</article>
    ${unplaced.length ? `
      <div class="bsf-ct-other">
        <h4 class="bsf-subsection">${esc(t("contract_other_changes"))}</h4>
        <p class="bsf-caption">${esc(t("contract_other_caption"))}</p>
        <ul class="bsf-mk-list">${unplaced.map((edit) => `
          <li><strong>${esc([t("clause"), edit.clause_number || edit.clause_id || ""].join(" ").trim())}</strong>
            ${editMarkup(edit)}</li>`).join("")}</ul>
      </div>` : ""}`;
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

  "new-case": (el) => openNewCaseForm(el.dataset.workflow || "litigation"),

  "archive-case": async (el) => {
    const archive = el.dataset.archived === "1";
    if (archive && !window.confirm(t("archive_confirm"))) return;
    try {
      await apiPost("/case/archive", { case_id: el.dataset.caseId, archived: archive });
      toast(t(archive ? "case_archived" : "case_restored"), "ok");
      await loadCases();
    } catch (error) { fail(error); }
  },

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


  "generate-pleading": async () => {
    const instructions = ($("#pleading-instructions") || {}).value || "";
    try {
      const language = ($("#pleading-language") || {}).value || preferredPleadingLanguage();
      await runJob(apiPost("/pleading/generate", { case_id: S.caseId, instructions, language }), "pleading-job");
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

  "download-contract-docx": () => {
    const url = backendUrl("/agreement/review_docx") + "?" + new URLSearchParams({
      case_id: S.caseId, lang: isRTL() ? "ar" : "en",
    }).toString();
    window.open(url, "_blank");
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

  "edit-fact-cell": (el) => {
    const row = el.closest("tr");
    if (row && !row.classList.contains("is-current")) {
      const rowId = el.dataset.rowId, field = el.dataset.field;
      goToReviewPage(row.dataset.pageId);
      const cell = document.querySelector(`[data-action="edit-fact-cell"][data-row-id="${CSS.escape(rowId)}"][data-field="${CSS.escape(field)}"]`);
      if (cell) startCellEdit(cell);
      return;
    }
    startCellEdit(el);
  },

  "review-goto-page": (el) => goToReviewPage(el.dataset.pageId),

  "review-step": (el) => {
    const { pages } = reviewState();
    const page = currentReviewPage(pages);
    const index = page ? pages.findIndex((item) => item.page_id === page.page_id) : 0;
    const next = pages[Math.min(pages.length - 1, Math.max(0, index + Number(el.dataset.step || 0)))];
    if (next) goToReviewPage(next.page_id);
  },

  "delete-fact": (el) => {
    if (!window.confirm(t("review_delete_confirm"))) return;
    return saveFactChange("/accounting/fact/delete", { row_id: el.dataset.rowId });
  },

  "restore-fact": (el) => saveFactChange("/accounting/fact/restore", { row_id: el.dataset.rowId }),

  "confirm-all-facts": async (el) => {
    const { facts } = reviewState();
    const uncertain = facts.filter((fact) => fact.status === "UNCERTAIN" && !fact.deleted).length;
    if (!window.confirm(t("review_confirm_all_prompt", { count: facts.filter((f) => !f.deleted).length, uncertain }))) return;
    el.disabled = true;
    const saved = await saveFactChange("/accounting/facts/confirm_all", {});
    if (saved) {
      toast(t("review_confirmed_toast"), "ok");
      await refreshCase();
      const box = document.querySelector('[data-action="accounting-synthesize"]');
      if (box) box.scrollIntoView({ behavior: "smooth", block: "center" });
    }
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
  "add-fact": async (form) => {
    const data = new FormData(form);
    const fields = {};
    ["date", "fact_type", "description", "amount", "balance", "currency"].forEach((name) => {
      const value = String(data.get(name) || "").trim();
      if (value) fields[name] = value;
    });
    S.reviewAddOpen = false;
    const saved = await saveFactChange("/accounting/fact/add", { page_id: form.dataset.pageId, fields });
    if (saved) toast(t("review_fact_added"), "ok");
  },

  "create-case": async (form) => {
    const data = new FormData(form);
    const workflow = form.dataset.workflow || "litigation";
    const body = { workflow_type: workflow };
    ["case_name", "language", "case_number", "client_name", "opposing_party", "case_type", "description",
     "contract_type", "counterparty"].forEach((name) => { if (data.has(name)) body[name] = String(data.get(name) || "").trim(); });
    try {
      const result = await apiPost("/create_case", body);
      closeModal();
      await loadCases();
      await openCase(result.case_id);
      // A new litigation case starts with its documents.
      if (workflow === "litigation") { S.tab = "documents"; showTab("case", S.tab); }
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
    if (actionEl && ACTIONS[actionEl.dataset.action] && !actionEl.matches("input, select")) {
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

    const statusFilter = event.target.closest('[data-action="dash-status-filter"]');
    if (statusFilter) { S.dash.status = statusFilter.value; renderLibrary(); return; }
    const archivedToggle = event.target.closest('[data-action="dash-archived"]');
    if (archivedToggle) { S.dash.archived = archivedToggle.checked; loadCases(); return; }

    const reviewSelect = event.target.closest('[data-action="review-select-page"]');
    if (reviewSelect) {
      goToReviewPage(reviewSelect.value);
      return;
    }

    const pleadingLang = event.target.closest('[data-action="select-pleading-lang"]');
    if (pleadingLang) {
      S.pleadingLang = pleadingLang.value;
      // Saved with the case, so the choice survives a refresh.
      apiPost("/state/persist", { case_id: S.caseId, state: { pleading_language: pleadingLang.value } }).catch(fail);
      if (S.snapshot && S.snapshot.workflow_state) S.snapshot.workflow_state.pleading_language = pleadingLang.value;
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
  bindSearch("#library-search", (value) => { S.dash.query = value; renderLibrary(); });
  bindSearch("#contract-search", (value) => { S.dash.contractQuery = value; renderLibrary(); });
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
    S.user = (await apiGet("/me")).user || "";
  } catch (error) {
    html(region("dash-litigation"), alertBox(t("sign_in_required"), "flag"));
    return;
  }
  renderSidebar();

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

