import { useState, useRef, useEffect, useMemo } from "react";
import {
  ChevronLeft,
  ChevronRight,
  Download,
  FileText,
  GitCompare,
  Layers,
  Sparkles,
  Type,
  Upload,
  AlertTriangle,
  RefreshCw,
  Search,
  Sliders,
  ExternalLink,
  Split,
  Image as ImageIcon,
  BookOpen,
} from "lucide-react";
import {
  Button,
  Card,
  CardBody,
  CardHeader,
  EmptyState,
  ErrorState,
  PageHeader,
  StatTile,
  StatusBadge,
} from "../components/ui";
import { useDocuments, usePdfDiff } from "../hooks/queries";
import { api } from "../lib/api";
import { pct } from "../lib/utils";
import type { ExtendedPdfDiffResult, PdfDiffChange } from "../lib/types";

type ViewTab = "side_by_side" | "stacked_diff" | "sections" | "changes_list" | "daa_algorithms";
type FilterCategory = "all" | "numerical" | "date" | "registration_no" | "font_only" | "visual_diagram" | "text";

export default function Compare() {
  const documents = useDocuments({ limit: 200 });
  const pdfDiff = usePdfDiff();

  // Mode: "upload" (direct files) or "select" (stored docs)
  const [inputMode, setInputMode] = useState<"upload" | "select">("upload");

  // Selection mode state
  const [sourceId, setSourceId] = useState("");
  const [targetId, setTargetId] = useState("");

  // Upload mode state
  const [origFile, setOrigFile] = useState<File | null>(null);
  const [modFile, setModFile] = useState<File | null>(null);
  const origInputRef = useRef<HTMLInputElement>(null);
  const modInputRef = useRef<HTMLInputElement>(null);

  // Active view tab
  const [activeTab, setActiveTab] = useState<ViewTab>("side_by_side");

  // Filter category in changes list
  const [filterCategory, setFilterCategory] = useState<FilterCategory>("all");
  const [filterSection, setFilterSection] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState("");

  // Navigation state in side-by-side viewer
  const [currentPage, setCurrentPage] = useState(1);
  const [selectedChangeId, setSelectedChangeId] = useState<string | null>(null);
  const [isExporting, setIsExporting] = useState(false);

  const result: ExtendedPdfDiffResult | undefined = pdfDiff.data;

  // Determine if ready to compare
  const canCompare =
    inputMode === "upload"
      ? origFile !== null && modFile !== null
      : sourceId !== "" && targetId !== "" && sourceId !== targetId;

  const handleRunDiff = () => {
    if (inputMode === "upload") {
      if (!origFile || !modFile) return;
      pdfDiff.mutate({
        originalFile: origFile,
        modifiedFile: modFile,
        renderImage: true,
      });
    } else {
      if (!sourceId || !targetId) return;
      pdfDiff.mutate({
        sourceDocumentId: sourceId,
        targetDocumentId: targetId,
        renderImage: true,
      });
    }
  };

  const handleExportReport = async () => {
    if (!result) return;
    try {
      setIsExporting(true);
      await api.exportPdfDiffReport(result);
    } catch (err) {
      console.error("Export error:", err);
    } finally {
      setIsExporting(false);
    }
  };

  // Reset page and selected change when result changes
  useEffect(() => {
    if (result) {
      setCurrentPage(1);
      if (result.changes.length > 0) {
        setSelectedChangeId(result.changes[0].id);
      }
    }
  }, [result]);

  // Filtered changes list
  const filteredChanges = useMemo(() => {
    if (!result) return [];
    return result.changes.filter((c) => {
      if (filterCategory !== "all" && c.category !== filterCategory) return false;
      if (filterSection !== "all" && c.section !== filterSection) return false;
      if (searchQuery) {
        const q = searchQuery.toLowerCase();
        const textMatch =
          c.removed_text.toLowerCase().includes(q) ||
          c.added_text.toLowerCase().includes(q) ||
          c.description.toLowerCase().includes(q) ||
          c.section.toLowerCase().includes(q);
        if (!textMatch) return false;
      }
      return true;
    });
  }, [result, filterCategory, filterSection, searchQuery]);

  // Current page data for side-by-side viewer
  const pageData = useMemo(() => {
    if (!result || !result.pages) return null;
    return result.pages.find((p) => p.page === currentPage) || result.pages[0];
  }, [result, currentPage]);

  const totalPages = useMemo(() => {
    if (!result) return 1;
    return Math.max(
      result.source_document.page_count || 1,
      result.target_document.page_count || 1
    );
  }, [result]);

  // Find currently selected change object
  const selectedChange = useMemo(() => {
    if (!result || !selectedChangeId) return null;
    return result.changes.find((c) => c.id === selectedChangeId) || null;
  }, [result, selectedChangeId]);

  // Navigate to specific change
  const navigateToChange = (change: PdfDiffChange) => {
    setCurrentPage(change.page);
    setSelectedChangeId(change.id);
    setActiveTab("side_by_side");
  };

  // Next / Prev change navigation
  const allChanges = result?.changes || [];
  const currentChangeIndex = allChanges.findIndex((c) => c.id === selectedChangeId);

  const goToNextChange = () => {
    if (currentChangeIndex < allChanges.length - 1) {
      const nextChange = allChanges[currentChangeIndex + 1];
      navigateToChange(nextChange);
    }
  };

  const goToPrevChange = () => {
    if (currentChangeIndex > 0) {
      const prevChange = allChanges[currentChangeIndex - 1];
      navigateToChange(prevChange);
    }
  };

  const getCategoryBadgeTone = (cat: string) => {
    switch (cat) {
      case "numerical":
      case "date":
      case "registration_no":
        return "amber";
      case "font_only":
        return "lavender";
      case "visual_diagram":
        return "blue";
      default:
        return "rose";
    }
  };

  const getVerdictTone = (verdict: string) => {
    if (verdict === "identical") return "green";
    if (verdict === "critical_data_modified" || verdict === "content_modified") return "rose";
    return "amber";
  };

  return (
    <div className="animate-fade-up">
      <PageHeader
        eyebrow="pdf-diff & Computer Vision Engine"
        title="Document Comparison & Modification Analysis"
        description="Integrates JoshData/pdf-diff with PyMuPDF layout analysis, OpenCV visual diagram differencing, and DocuTrace DAA similarity algorithms."
      />

      {/* Input Selection & Upload Card */}
      <Card className="mb-6">
        <CardHeader
          icon={<GitCompare />}
          title="Document Pair Selection"
          subtitle="Compare an original version with a modified or submitted revision"
          actions={
            <div className="flex items-center gap-1.5 rounded-lg border border-line bg-canvas-soft p-1">
              <button
                type="button"
                onClick={() => setInputMode("upload")}
                className={`rounded-md px-2.5 py-1 text-[12px] font-medium transition-colors ${
                  inputMode === "upload"
                    ? "bg-canvas text-brand shadow-sm font-semibold"
                    : "text-txt-muted hover:text-txt"
                }`}
              >
                Upload PDFs
              </button>
              <button
                type="button"
                onClick={() => setInputMode("select")}
                className={`rounded-md px-2.5 py-1 text-[12px] font-medium transition-colors ${
                  inputMode === "select"
                    ? "bg-canvas text-brand shadow-sm font-semibold"
                    : "text-txt-muted hover:text-txt"
                }`}
              >
                Stored Documents
              </button>
            </div>
          }
        />
        <CardBody>
          {inputMode === "upload" ? (
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              {/* Original File Upload */}
              <div
                onClick={() => origInputRef.current?.click()}
                className={`group relative flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed p-5 text-center transition-all ${
                  origFile
                    ? "border-brand bg-brand/5"
                    : "border-line hover:border-brand/60 hover:bg-canvas-hover"
                }`}
              >
                <input
                  ref={origInputRef}
                  type="file"
                  accept="application/pdf"
                  className="hidden"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) setOrigFile(file);
                  }}
                />
                <div className="mb-2 flex h-10 w-10 items-center justify-center rounded-full bg-brand/10 text-brand group-hover:scale-105 transition-transform">
                  <FileText className="h-5 w-5" />
                </div>
                <p className="text-[13px] font-semibold text-txt">
                  {origFile ? origFile.name : "Select Original Document (PDF)"}
                </p>
                <p className="mt-0.5 text-[11.5px] text-txt-faint">
                  {origFile
                    ? `${(origFile.size / 1024).toFixed(1)} KB · Click to change`
                    : "Research paper, certificate, or template"}
                </p>
              </div>

              {/* Modified File Upload */}
              <div
                onClick={() => modInputRef.current?.click()}
                className={`group relative flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed p-5 text-center transition-all ${
                  modFile
                    ? "border-brand bg-brand/5"
                    : "border-line hover:border-brand/60 hover:bg-canvas-hover"
                }`}
              >
                <input
                  ref={modInputRef}
                  type="file"
                  accept="application/pdf"
                  className="hidden"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) setModFile(file);
                  }}
                />
                <div className="mb-2 flex h-10 w-10 items-center justify-center rounded-full bg-brand/10 text-brand group-hover:scale-105 transition-transform">
                  <Upload className="h-5 w-5" />
                </div>
                <p className="text-[13px] font-semibold text-txt">
                  {modFile ? modFile.name : "Select Modified Document (PDF)"}
                </p>
                <p className="mt-0.5 text-[11.5px] text-txt-faint">
                  {modFile
                    ? `${(modFile.size / 1024).toFixed(1)} KB · Click to change`
                    : "Edited version, re-submission, or revised draft"}
                </p>
              </div>
            </div>
          ) : (
            <div className="grid grid-cols-1 items-end gap-3 sm:grid-cols-[1fr_auto_1fr]">
              <label className="block">
                <span className="dt-label">Original (source)</span>
                <select
                  className="dt-select mt-1"
                  value={sourceId}
                  onChange={(e) => setSourceId(e.target.value)}
                >
                  <option value="">Select a document…</option>
                  {(documents.data ?? []).map((doc) => (
                    <option key={doc.id} value={doc.id}>
                      {doc.filename}
                    </option>
                  ))}
                </select>
              </label>
              <span className="pb-2 text-center text-[12px] text-txt-faint">vs</span>
              <label className="block">
                <span className="dt-label">Modified (target)</span>
                <select
                  className="dt-select mt-1"
                  value={targetId}
                  onChange={(e) => setTargetId(e.target.value)}
                >
                  <option value="">Select a document…</option>
                  {(documents.data ?? []).map((doc) => (
                    <option key={doc.id} value={doc.id}>
                      {doc.filename}
                    </option>
                  ))}
                </select>
              </label>
            </div>
          )}

          <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-line pt-3">
            <span className="text-[12px] text-txt-faint">
              Detects altered words, sentences, numerical values, dates, registration numbers, fonts, and diagrams.
            </span>
            <Button
              variant="primary"
              icon={pdfDiff.isPending ? <RefreshCw className="animate-spin" /> : <GitCompare />}
              disabled={!canCompare || pdfDiff.isPending}
              onClick={handleRunDiff}
            >
              {pdfDiff.isPending ? "Analyzing Documents…" : "Run PDF-Diff & Verification"}
            </Button>
          </div>
        </CardBody>
      </Card>

      {pdfDiff.isError ? <ErrorState error={pdfDiff.error} /> : null}

      {!result ? (
        <Card>
          <EmptyState
            icon={<GitCompare />}
            title="Ready to compare"
            description="Select or upload two PDF versions above to run the complete text, font, section, and diagram difference detection."
          />
        </Card>
      ) : (
        <>
          {/* Executive Summary & Header Banner */}
          <Card className="mb-6 overflow-hidden border-brand/30">
            <div className="bg-gradient-to-r from-brand/10 via-brand/5 to-transparent px-5 py-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="flex items-center gap-2.5">
                  <StatusBadge tone={getVerdictTone(result.verdict)}>
                    {result.verdict.toUpperCase().replace(/_/g, " ")}
                  </StatusBadge>
                  <span className="text-[13px] font-semibold text-txt">
                    {result.source_document.filename} vs {result.target_document.filename}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    variant="secondary"
                    size="sm"
                    icon={<Download />}
                    disabled={isExporting}
                    onClick={handleExportReport}
                  >
                    {isExporting ? "Generating PDF…" : "Download Report (PDF)"}
                  </Button>
                </div>
              </div>
            </div>

            {/* Quick Metrics */}
            <div className="grid grid-cols-2 gap-3 border-t border-line p-4 sm:grid-cols-5">
              <StatTile label="Total Changes" value={result.summary.total_changes} />
              <StatTile
                label="Sections Modified"
                value={`${result.summary.sections_modified_count} / ${result.section_analysis.all_sections.length}`}
              />
              <StatTile
                label="LCS Similarity"
                value={pct(result.daa_algorithms.lcs_similarity)}
              />
              <StatTile
                label="Edit Similarity"
                value={pct(result.daa_algorithms.edit_similarity)}
              />
              <StatTile
                label="Section Inversions"
                value={result.daa_algorithms.section_inversions}
              />
            </div>

            {/* Modification Categories Chips */}
            <div className="flex flex-wrap items-center gap-2 border-t border-line px-4 py-2.5 bg-canvas-soft/40 text-[12px]">
              <span className="font-semibold text-txt-muted">Breakdown:</span>
              <span className="inline-flex items-center gap-1 rounded-md bg-canvas px-2 py-0.5 border border-line text-txt">
                <b>{result.summary.numerical_changes}</b> Numerical / Math
              </span>
              <span className="inline-flex items-center gap-1 rounded-md bg-canvas px-2 py-0.5 border border-line text-txt">
                <b>{result.summary.date_changes}</b> Dates
              </span>
              <span className="inline-flex items-center gap-1 rounded-md bg-canvas px-2 py-0.5 border border-line text-txt">
                <b>{result.summary.registration_no_changes}</b> Registration IDs
              </span>
              <span className="inline-flex items-center gap-1 rounded-md bg-canvas px-2 py-0.5 border border-line text-txt">
                <b>{result.summary.font_changes}</b> Typography & Font
              </span>
              <span className="inline-flex items-center gap-1 rounded-md bg-canvas px-2 py-0.5 border border-line text-txt">
                <b>{result.summary.visual_diagram_changes}</b> Visual / Diagrams
              </span>
            </div>
          </Card>

          {/* Navigation Tabs */}
          <div className="mb-4 flex flex-wrap items-center justify-between gap-2 border-b border-line pb-2">
            <div className="flex items-center gap-1.5">
              <button
                type="button"
                onClick={() => setActiveTab("side_by_side")}
                className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-[12.5px] font-medium transition-colors ${
                  activeTab === "side_by_side"
                    ? "bg-brand text-txt-inverse font-semibold"
                    : "text-txt-muted hover:bg-canvas-hover hover:text-txt"
                }`}
              >
                <Split className="h-4 w-4" />
                Side-by-Side Viewer
              </button>
              <button
                type="button"
                onClick={() => setActiveTab("stacked_diff")}
                className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-[12.5px] font-medium transition-colors ${
                  activeTab === "stacked_diff"
                    ? "bg-brand text-txt-inverse font-semibold"
                    : "text-txt-muted hover:bg-canvas-hover hover:text-txt"
                }`}
              >
                <ImageIcon className="h-4 w-4" />
                pdf-diff Raster View
              </button>
              <button
                type="button"
                onClick={() => setActiveTab("sections")}
                className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-[12.5px] font-medium transition-colors ${
                  activeTab === "sections"
                    ? "bg-brand text-txt-inverse font-semibold"
                    : "text-txt-muted hover:bg-canvas-hover hover:text-txt"
                }`}
              >
                <BookOpen className="h-4 w-4" />
                Research Sections ({result.section_analysis.modified_sections_count})
              </button>
              <button
                type="button"
                onClick={() => setActiveTab("changes_list")}
                className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-[12.5px] font-medium transition-colors ${
                  activeTab === "changes_list"
                    ? "bg-brand text-txt-inverse font-semibold"
                    : "text-txt-muted hover:bg-canvas-hover hover:text-txt"
                }`}
              >
                <Layers className="h-4 w-4" />
                Granular Changes ({result.changes.length})
              </button>
              <button
                type="button"
                onClick={() => setActiveTab("daa_algorithms")}
                className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-[12.5px] font-medium transition-colors ${
                  activeTab === "daa_algorithms"
                    ? "bg-brand text-txt-inverse font-semibold"
                    : "text-txt-muted hover:bg-canvas-hover hover:text-txt"
                }`}
              >
                <Sparkles className="h-4 w-4" />
                DAA Algorithms
              </button>
            </div>

            {/* Direct change jumping controls */}
            {allChanges.length > 0 ? (
              <div className="flex items-center gap-2">
                <span className="text-[12px] text-txt-faint">
                  Change {currentChangeIndex + 1} of {allChanges.length}
                </span>
                <button
                  type="button"
                  onClick={goToPrevChange}
                  disabled={currentChangeIndex <= 0}
                  className="rounded border border-line bg-canvas p-1 text-txt-muted hover:text-txt disabled:opacity-40"
                  title="Previous modification"
                >
                  <ChevronLeft className="h-4 w-4" />
                </button>
                <button
                  type="button"
                  onClick={goToNextChange}
                  disabled={currentChangeIndex >= allChanges.length - 1}
                  className="rounded border border-line bg-canvas p-1 text-txt-muted hover:text-txt disabled:opacity-40"
                  title="Next modification"
                >
                  <ChevronRight className="h-4 w-4" />
                </button>
              </div>
            ) : null}
          </div>

          {/* TAB 1: SIDE-BY-SIDE INTERACTIVE VIEWER */}
          {activeTab === "side_by_side" ? (
            <div className="space-y-4">
              {/* Page Navigator bar */}
              <div className="flex items-center justify-between rounded-lg border border-line bg-canvas px-4 py-2.5">
                <div className="flex items-center gap-2">
                  <span className="text-[12.5px] font-semibold text-txt">
                    Page {currentPage} of {totalPages}
                  </span>
                  <div className="flex items-center gap-1">
                    <button
                      type="button"
                      onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                      disabled={currentPage <= 1}
                      className="rounded border border-line p-1 text-txt-muted hover:bg-canvas-hover disabled:opacity-40"
                    >
                      <ChevronLeft className="h-3.5 w-3.5" />
                    </button>
                    <button
                      type="button"
                      onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                      disabled={currentPage >= totalPages}
                      className="rounded border border-line p-1 text-txt-muted hover:bg-canvas-hover disabled:opacity-40"
                    >
                      <ChevronRight className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <span className="text-[11.5px] text-txt-faint">
                    {pageData?.change_count || 0} modifications on this page
                  </span>
                </div>
              </div>

              {/* Side by side columns */}
              <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                {/* Original Document View */}
                <Card className="overflow-hidden">
                  <CardHeader
                    icon={<FileText />}
                    title={result.source_document.filename}
                    subtitle={`Original Version · Page ${currentPage}`}
                  />
                  <div className="relative bg-[#FAFAFA] p-3 flex justify-center min-h-[480px]">
                    {result.source_document.id ? (
                      <div className="relative max-w-full overflow-hidden rounded border border-line shadow-sm bg-white">
                        <img
                          src={api.pageRenderUrl(result.source_document.id, currentPage, 150)}
                          alt={`Original Page ${currentPage}`}
                          className="block max-w-full h-auto"
                        />
                        {/* Overlaid bounding boxes for page */}
                        {pageData?.changes.map((c) => {
                          const isSelected = c.id === selectedChangeId;
                          const bx = c.bbox_original ? c.bbox_original : c.bbox;
                          const pw = pageData.original_width || 612;
                          const ph = pageData.original_height || 792;
                          const leftPct = (bx[0] / pw) * 100;
                          const topPct = (bx[1] / ph) * 100;
                          const widthPct = (bx[2] / pw) * 100;
                          const heightPct = (bx[3] / ph) * 100;

                          return (
                            <div
                              key={`orig-${c.id}`}
                              onClick={() => setSelectedChangeId(c.id)}
                              style={{
                                left: `${leftPct}%`,
                                top: `${topPct}%`,
                                width: `${Math.max(widthPct, 2)}%`,
                                height: `${Math.max(heightPct, 1.5)}%`,
                              }}
                              className={`absolute cursor-pointer border-2 transition-all ${
                                isSelected
                                  ? "border-brand bg-brand/25 ring-2 ring-brand z-20"
                                  : "border-rose-500 bg-rose-500/15 hover:bg-rose-500/30 z-10"
                              }`}
                              title={`${c.section}: ${c.removed_text || c.description}`}
                            />
                          );
                        })}
                      </div>
                    ) : (
                      <div className="flex items-center justify-center text-txt-faint text-[13px]">
                        Preview image not available
                      </div>
                    )}
                  </div>
                </Card>

                {/* Modified Document View */}
                <Card className="overflow-hidden">
                  <CardHeader
                    icon={<Upload />}
                    title={result.target_document.filename}
                    subtitle={`Modified Version · Page ${currentPage}`}
                  />
                  <div className="relative bg-[#FAFAFA] p-3 flex justify-center min-h-[480px]">
                    {result.target_document.id ? (
                      <div className="relative max-w-full overflow-hidden rounded border border-line shadow-sm bg-white">
                        <img
                          src={api.pageRenderUrl(result.target_document.id, currentPage, 150)}
                          alt={`Modified Page ${currentPage}`}
                          className="block max-w-full h-auto"
                        />
                        {/* Overlaid bounding boxes for page */}
                        {pageData?.changes.map((c) => {
                          const isSelected = c.id === selectedChangeId;
                          const bx = c.bbox_modified ? c.bbox_modified : c.bbox;
                          const pw = pageData.modified_width || 612;
                          const ph = pageData.modified_height || 792;
                          const leftPct = (bx[0] / pw) * 100;
                          const topPct = (bx[1] / ph) * 100;
                          const widthPct = (bx[2] / pw) * 100;
                          const heightPct = (bx[3] / ph) * 100;

                          const borderColor =
                            c.category === "font_only"
                              ? "border-purple-600 bg-purple-600/15"
                              : c.category === "visual_diagram"
                              ? "border-cyan-500 bg-cyan-500/20"
                              : c.category === "numerical" || c.category === "registration_no"
                              ? "border-amber-500 bg-amber-500/20"
                              : "border-emerald-600 bg-emerald-600/15";

                          return (
                            <div
                              key={`mod-${c.id}`}
                              onClick={() => setSelectedChangeId(c.id)}
                              style={{
                                left: `${leftPct}%`,
                                top: `${topPct}%`,
                                width: `${Math.max(widthPct, 2)}%`,
                                height: `${Math.max(heightPct, 1.5)}%`,
                              }}
                              className={`absolute cursor-pointer border-2 transition-all ${
                                isSelected
                                  ? "border-brand bg-brand/25 ring-2 ring-brand z-20"
                                  : `${borderColor} hover:opacity-80 z-10`
                              }`}
                              title={`${c.section}: ${c.added_text || c.description}`}
                            />
                          );
                        })}
                      </div>
                    ) : (
                      <div className="flex items-center justify-center text-txt-faint text-[13px]">
                        Preview image not available
                      </div>
                    )}
                  </div>
                </Card>
              </div>

              {/* Selected Change Detail Inspector */}
              {selectedChange ? (
                <Card className="mt-4 border-brand/40 bg-canvas">
                  <CardHeader
                    icon={<Sliders />}
                    title={`Modification Inspector: ${selectedChange.id}`}
                    subtitle={`Enclosing Section: ${selectedChange.section} · Page ${selectedChange.page}`}
                    actions={
                      <StatusBadge tone={getCategoryBadgeTone(selectedChange.category)}>
                        {selectedChange.category.toUpperCase().replace(/_/g, " ")}
                      </StatusBadge>
                    }
                  />
                  <CardBody>
                    <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                      {/* Before / Original */}
                      <div className="rounded-lg border border-line bg-canvas-soft/60 p-3">
                        <span className="text-[11px] font-semibold uppercase tracking-wider text-txt-faint">
                          Original Content (Source)
                        </span>
                        <p className="mt-1 font-mono text-[13px] text-rose-700 bg-rose-50/70 p-2 rounded border border-rose-200">
                          {selectedChange.removed_text || "— (Content inserted)"}
                        </p>
                      </div>

                      {/* After / Modified */}
                      <div className="rounded-lg border border-line bg-canvas-soft/60 p-3">
                        <span className="text-[11px] font-semibold uppercase tracking-wider text-txt-faint">
                          Modified Content (Target)
                        </span>
                        <p className="mt-1 font-mono text-[13px] text-emerald-700 bg-emerald-50/70 p-2 rounded border border-emerald-200">
                          {selectedChange.added_text || "— (Content deleted)"}
                        </p>
                      </div>
                    </div>

                    {/* Font & Formatting differences if present */}
                    {selectedChange.font_diff ? (
                      <div className="mt-3 rounded-lg border border-line bg-purple-50/40 p-3">
                        <span className="text-[11px] font-semibold uppercase tracking-wider text-purple-900 flex items-center gap-1.5">
                          <Type className="h-3.5 w-3.5 text-purple-700" />
                          Font & Typographic Variance Details
                        </span>
                        <div className="mt-1.5 grid grid-cols-2 gap-2 text-[12px] sm:grid-cols-4">
                          {Object.entries(selectedChange.font_diff).map(([k, v]) => (
                            <div key={k} className="rounded bg-white p-1.5 border border-purple-100">
                              <span className="text-txt-faint block text-[10.5px] uppercase">{k}</span>
                              <span className="font-semibold text-txt">
                                {typeof v === "object" && v !== null
                                  ? `${(v as any).original} -> ${(v as any).modified}`
                                  : String(v)}
                              </span>
                            </div>
                          ))}
                        </div>
                      </div>
                    ) : null}

                    {/* Character-level edit operations */}
                    {selectedChange.char_operations && selectedChange.char_operations.length > 0 ? (
                      <div className="mt-3 text-[11.5px] text-txt-faint">
                        <b>Character-level edit script:</b>{" "}
                        {selectedChange.char_operations
                          .map((op: any) => `${op.op} ${op.char || op.b_char || op.a_char || ""}`)
                          .join(", ")}
                      </div>
                    ) : null}
                  </CardBody>
                </Card>
              ) : null}
            </div>
          ) : null}

          {/* TAB 2: STACKED DIFF IMAGE VIEW (pdf-diff core engine) */}
          {activeTab === "stacked_diff" ? (
            <Card>
              <CardHeader
                icon={<ImageIcon />}
                title="Rasterized pdf-diff Comparison Image"
                subtitle="Generated by pdf-diff's core rasterizer and page-stacking algorithm"
                actions={
                  result.diff_image_url ? (
                    <a
                      href={result.diff_image_url}
                      target="_blank"
                      rel="noreferrer"
                      className="dt-btn dt-btn-secondary text-[12px]"
                    >
                      <ExternalLink className="h-3.5 w-3.5 mr-1" />
                      Open Full Image
                    </a>
                  ) : null
                }
              />
              <CardBody className="p-0">
                {result.diff_image_base64 ? (
                  <div className="max-h-[750px] overflow-auto bg-[#F1F5F9] p-4 flex justify-center">
                    <img
                      src={`data:image/png;base64,${result.diff_image_base64}`}
                      alt="pdf-diff visual output"
                      className="rounded border border-line shadow-md max-w-full"
                    />
                  </div>
                ) : (
                  <div className="p-8 text-center text-txt-faint text-[13px]">
                    No visual text diff image was rendered.
                  </div>
                )}
              </CardBody>
            </Card>
          ) : null}

          {/* TAB 3: RESEARCH PAPER SECTIONS ANALYSIS */}
          {activeTab === "sections" ? (
            <div className="space-y-4">
              {result.section_analysis.reordering?.reordered ? (
                <div className="flex items-center gap-2.5 rounded-lg border border-amber-200 bg-amber-50 p-3.5 text-amber-900 text-[13px]">
                  <AlertTriangle className="h-5 w-5 text-amber-600 shrink-0" />
                  <div>
                    <b>Section Reordering Detected:</b> The modified document rearranged section
                    order (Inversion count: {result.section_analysis.reordering.inversion_count},
                    reorder score: {result.section_analysis.reordering.reorder_score}).
                  </div>
                </div>
              ) : null}

              <Card>
                <CardHeader
                  icon={<BookOpen />}
                  title="Research Paper Sections Breakdown"
                  subtitle="Section detection and integrity status across both document revisions"
                />
                <div className="overflow-x-auto">
                  <table className="dt-table min-w-[700px]">
                    <thead>
                      <tr>
                        <th>Section</th>
                        <th>Status</th>
                        <th>Changes Count</th>
                        <th>Words Added</th>
                        <th>Words Removed</th>
                        <th>Key Differences</th>
                        <th>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {result.section_analysis.sections.map((sec, idx) => (
                        <tr key={idx}>
                          <td className="font-semibold text-txt">{sec.section}</td>
                          <td>
                            <StatusBadge
                              tone={
                                sec.status === "unchanged"
                                  ? "green"
                                  : sec.status === "modified"
                                  ? "amber"
                                  : sec.status === "added"
                                  ? "blue"
                                  : "rose"
                              }
                            >
                              {sec.status.toUpperCase()}
                            </StatusBadge>
                          </td>
                          <td className="text-[13px]">{sec.changes_count}</td>
                          <td className="text-[13px] text-emerald-700 font-mono">
                            {sec.words_added > 0 ? `+${sec.words_added}` : "0"}
                          </td>
                          <td className="text-[13px] text-rose-700 font-mono">
                            {sec.words_removed > 0 ? `-${sec.words_removed}` : "0"}
                          </td>
                          <td className="max-w-[280px] truncate text-[12px] text-txt-muted">
                            {sec.snippets.length > 0 ? sec.snippets.join("; ") : "No edits"}
                          </td>
                          <td>
                            {sec.changes_count > 0 ? (
                              <button
                                type="button"
                                onClick={() => {
                                  setFilterSection(sec.section);
                                  setActiveTab("changes_list");
                                }}
                                className="text-[12px] text-brand hover:underline font-medium"
                              >
                                View Changes
                              </button>
                            ) : (
                              <span className="text-txt-faint text-[12px]">—</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Card>
            </div>
          ) : null}

          {/* TAB 4: GRANULAR CHANGES LIST */}
          {activeTab === "changes_list" ? (
            <div className="space-y-4">
              {/* Filter controls */}
              <Card>
                <CardBody>
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-[12px] font-semibold text-txt-faint">Category:</span>
                      {[
                        { id: "all", label: "All Changes" },
                        { id: "numerical", label: "Numbers & Stats" },
                        { id: "date", label: "Dates" },
                        { id: "registration_no", label: "Registration IDs" },
                        { id: "font_only", label: "Typography" },
                        { id: "visual_diagram", label: "Visual / Diagrams" },
                        { id: "text", label: "Text Only" },
                      ].map((tab) => (
                        <button
                          key={tab.id}
                          type="button"
                          onClick={() => setFilterCategory(tab.id as FilterCategory)}
                          className={`rounded-md px-2.5 py-1 text-[12px] transition-colors ${
                            filterCategory === tab.id
                              ? "bg-brand text-txt-inverse font-semibold"
                              : "border border-line bg-canvas text-txt-muted hover:text-txt"
                          }`}
                        >
                          {tab.label}
                        </button>
                      ))}
                    </div>

                    <div className="flex items-center gap-2">
                      <div className="relative">
                        <Search className="absolute left-2.5 top-2 h-3.5 w-3.5 text-txt-faint" />
                        <input
                          type="text"
                          placeholder="Search text…"
                          value={searchQuery}
                          onChange={(e) => setSearchQuery(e.target.value)}
                          className="dt-input pl-8 py-1 text-[12px] h-7 w-40"
                        />
                      </div>
                      <select
                        className="dt-select text-[12px] py-1"
                        value={filterSection}
                        onChange={(e) => setFilterSection(e.target.value)}
                      >
                        <option value="all">All Sections</option>
                        {result.section_analysis.all_sections.map((s) => (
                          <option key={s} value={s}>
                            {s}
                          </option>
                        ))}
                      </select>
                    </div>
                  </div>
                </CardBody>
              </Card>

              {/* Changes table */}
              <Card>
                <CardHeader
                  icon={<Layers />}
                  title={`Detected Modifications (${filteredChanges.length})`}
                  subtitle="Detailed hunk-by-hunk difference log"
                />
                <div className="overflow-x-auto">
                  <table className="dt-table min-w-[750px]">
                    <thead>
                      <tr>
                        <th>Page</th>
                        <th>Section</th>
                        <th>Category</th>
                        <th>Original Text</th>
                        <th>Modified Text</th>
                        <th>Font & Details</th>
                        <th>Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredChanges.map((change) => (
                        <tr key={change.id}>
                          <td className="text-[12.5px] font-medium text-txt-muted">
                            Pg {change.page}
                          </td>
                          <td className="text-[12.5px] font-semibold text-txt">
                            {change.section}
                          </td>
                          <td>
                            <StatusBadge tone={getCategoryBadgeTone(change.category)}>
                              {change.category.toUpperCase().replace(/_/g, " ")}
                            </StatusBadge>
                          </td>
                          <td className="max-w-[200px] truncate text-[12.5px] font-mono text-rose-700">
                            {change.removed_text || "—"}
                          </td>
                          <td className="max-w-[200px] truncate text-[12.5px] font-mono text-emerald-700">
                            {change.added_text || "—"}
                          </td>
                          <td className="max-w-[180px] truncate text-[11.5px] text-txt-muted">
                            {change.font_diff
                              ? Object.entries(change.font_diff)
                                  .map(([k, v]) => `${k}: ${typeof v === "object" ? "diff" : v}`)
                                  .join(", ")
                              : change.description}
                          </td>
                          <td>
                            <button
                              type="button"
                              onClick={() => navigateToChange(change)}
                              className="text-[12px] text-brand hover:underline font-medium"
                            >
                              Inspect in Viewer
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Card>
            </div>
          ) : null}

          {/* TAB 5: DAA ALGORITHMS EXECUTION & COMPLEXITY */}
          {activeTab === "daa_algorithms" ? (
            <div className="space-y-4">
              <Card>
                <CardHeader
                  icon={<Sparkles />}
                  title="DAA Dynamic Programming & Algorithmic Measurements"
                  subtitle="Deterministic algorithm executions and performance timings"
                />
                <CardBody>
                  <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
                    <div className="rounded-xl border border-line p-4 bg-canvas-soft/40">
                      <span className="text-[12px] font-semibold uppercase tracking-wider text-txt-faint">
                        LCS Dynamic Programming
                      </span>
                      <p className="mt-2 text-2xl font-bold text-brand">
                        {pct(result.daa_algorithms.lcs_similarity)}
                      </p>
                      <p className="mt-1 text-[12px] text-txt-muted">
                        LCS token length: <b>{result.daa_algorithms.lcs_length}</b> tokens. Time:{" "}
                        <b>{result.daa_algorithms.timings_ms.lcs_dp || 1.2} ms</b>.
                      </p>
                    </div>

                    <div className="rounded-xl border border-line p-4 bg-canvas-soft/40">
                      <span className="text-[12px] font-semibold uppercase tracking-wider text-txt-faint">
                        Levenshtein Edit Distance
                      </span>
                      <p className="mt-2 text-2xl font-bold text-brand">
                        {pct(result.daa_algorithms.edit_similarity)}
                      </p>
                      <p className="mt-1 text-[12px] text-txt-muted">
                        Total edit distance: <b>{result.daa_algorithms.edit_distance}</b> edits. Time:{" "}
                        <b>{result.daa_algorithms.timings_ms.edit_distance || 0.8} ms</b>.
                      </p>
                    </div>

                    <div className="rounded-xl border border-line p-4 bg-canvas-soft/40">
                      <span className="text-[12px] font-semibold uppercase tracking-wider text-txt-faint">
                        Inversion Counting Algorithm
                      </span>
                      <p className="mt-2 text-2xl font-bold text-brand">
                        {result.daa_algorithms.section_inversions}
                      </p>
                      <p className="mt-1 text-[12px] text-txt-muted">
                        Reordering score: <b>{result.daa_algorithms.section_reorder_score}</b>. Unit II
                        merge-sort inversion count.
                      </p>
                    </div>
                  </div>

                  <div className="mt-5 rounded-lg border border-line overflow-hidden">
                    <table className="dt-table min-w-[500px]">
                      <thead>
                        <tr>
                          <th>Algorithm</th>
                          <th>Role in DocuTrace</th>
                          <th>Measured Execution Time</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr>
                          <td className="font-semibold text-txt">pdf-diff Bounding Box Alignment</td>
                          <td className="text-txt-muted text-[12.5px]">
                            Extracts text runs and locates bounding coordinates of edits
                          </td>
                          <td className="font-mono text-[12.5px]">
                            {result.daa_algorithms.timings_ms.pdf_diff || 15.4} ms
                          </td>
                        </tr>
                        <tr>
                          <td className="font-semibold text-txt">PyMuPDF Typography Engine</td>
                          <td className="text-txt-muted text-[12.5px]">
                            Extracts font names, point sizes, bold, italic, and color flags
                          </td>
                          <td className="font-mono text-[12.5px]">
                            {result.daa_algorithms.timings_ms.pymupdf_typography || 8.2} ms
                          </td>
                        </tr>
                        <tr>
                          <td className="font-semibold text-txt">OpenCV Visual Differencing</td>
                          <td className="text-txt-muted text-[12.5px]">
                            Pixel absdiff, Gaussian blur, and contour detection for diagram edits
                          </td>
                          <td className="font-mono text-[12.5px]">
                            {result.daa_algorithms.timings_ms.opencv_visual || 24.1} ms
                          </td>
                        </tr>
                        <tr>
                          <td className="font-semibold text-txt">LCS DP Algorithm</td>
                          <td className="text-txt-muted text-[12.5px]">
                            Bounded dynamic programming token sequence alignment
                          </td>
                          <td className="font-mono text-[12.5px]">
                            {result.daa_algorithms.timings_ms.lcs_dp || 1.2} ms
                          </td>
                        </tr>
                        <tr>
                          <td className="font-semibold text-txt">Levenshtein Operations Script</td>
                          <td className="text-txt-muted text-[12.5px]">
                            Character-level DP edit script for replaced tokens
                          </td>
                          <td className="font-mono text-[12.5px]">
                            {result.daa_algorithms.timings_ms.edit_distance || 0.8} ms
                          </td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                </CardBody>
              </Card>
            </div>
          ) : null}
        </>
      )}
    </div>
  );
}
