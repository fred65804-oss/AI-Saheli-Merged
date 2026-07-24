"use client";

import { useEffect, useMemo, useState } from "react";
import {
  BookOpen,
  CheckCircle2,
  CircleHelp,
  ClipboardCheck,
  Info,
  Landmark,
  LoaderCircle,
  MapPin,
  Phone,
  Search,
  XCircle,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { RequireAuth } from "@/components/require-auth";
import {
  getMeta,
  toolEligibility,
  toolGeo,
  toolHelpline,
  toolKbSearch,
  type AppMeta,
  type EligibilityResult,
  type Facility,
  type HelplineEntry,
  type KBChunk,
  type RuleResult,
} from "@/lib/api";
import { cn } from "@/lib/utils";

// --------------------------------------------------------------------------- //
// The tool explorer is 100% data-driven: enum choices and the eligibility
// form all come from /meta (which reads the same Pydantic models / capability
// cards the orchestrator uses). Nothing scheme-specific is hardcoded here.
// --------------------------------------------------------------------------- //

type ToolTab = "kb" | "eligibility" | "geo" | "helpline";

const TABS: { id: ToolTab; label: string; icon: typeof Search }[] = [
  { id: "kb", label: "Knowledge base", icon: BookOpen },
  { id: "eligibility", label: "Eligibility", icon: Landmark },
  { id: "geo", label: "Facility locator", icon: MapPin },
  { id: "helpline", label: "Helplines", icon: Phone },
];

export default function ToolsPage() {
  return (
    <RequireAuth requireAdmin>
      <ToolsExplorer />
    </RequireAuth>
  );
}

function ToolsExplorer() {
  const [meta, setMeta] = useState<AppMeta | null>(null);
  const [tab, setTab] = useState<ToolTab>("kb");
  const [metaError, setMetaError] = useState<string | null>(null);

  useEffect(() => {
    getMeta()
      .then(setMeta)
      .catch((e) => setMetaError(e.message || "Could not load /meta"));
  }, []);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="mb-1 text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">
            Staff workspace
          </div>
          <h1 className="font-display text-2xl font-semibold tracking-tight text-ministry">Service tools</h1>
          <p className="text-sm text-muted-foreground">
            Search official guidance, check scheme eligibility, and locate support services.
          </p>
        </div>
        <div
          role="tablist"
          aria-label="Service tools"
          className="flex overflow-hidden rounded-lg border bg-white p-1 shadow-sm"
        >
          {TABS.map((t) => {
            const Icon = t.icon;
            return (
                <button
                  key={t.id}
                  type="button"
                  role="tab"
                  aria-selected={tab === t.id}
                  onClick={() => setTab(t.id)}
                  className={cn(
                    "flex items-center gap-1.5 rounded-md px-4 py-2 text-xs font-medium transition-all",
                    tab === t.id
                      ? "gradient-ministry text-white shadow-sm"
                      : "text-muted-foreground hover:bg-ministry-soft"
                )}
              >
                <Icon className="h-3.5 w-3.5" /> {t.label}
              </button>
            );
          })}
        </div>
      </div>

      {metaError && (
        <div role="alert" className="rounded-lg border border-destructive/40 bg-destructive/10 px-4 py-2 text-sm text-destructive">
          {metaError}
        </div>
      )}

      {tab === "kb" && <KbSearchPanel enums={meta?.enums} />}
      {tab === "eligibility" && <EligibilityPanel schema={meta?.eligibility_schema} />}
      {tab === "geo" && <GeoPanel enums={meta?.enums} />}
      {tab === "helpline" && <HelplinePanel enums={meta?.enums} />}
    </div>
  );
}

function LatencyBadge({ ms }: { ms: number }) {
  return <Badge variant="muted">{ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toFixed(1)} s`}</Badge>;
}

function SelectField({
  label,
  value,
  onChange,
  options,
  allowEmpty,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: string[];
  allowEmpty?: string;
}) {
  return (
    <label className="block text-sm">
      <span className="mb-1 block text-xs font-medium text-foreground">{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="h-11 w-full rounded-md border border-input bg-white px-3 py-2 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
      >
        {allowEmpty !== undefined && <option value="">{allowEmpty}</option>}
        {options.map((o) => (
          <option key={o} value={o}>
            {o.replaceAll("_", " ")}
          </option>
        ))}
      </select>
    </label>
  );
}

// --------------------------------------------------------------------------- //
// Knowledge base search
// --------------------------------------------------------------------------- //
function KbSearchPanel({ enums }: { enums?: Record<string, string[]> }) {
  const [query, setQuery] = useState("What does a pregnant woman get under PMMVY?");
  const [scheme, setScheme] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [chunks, setChunks] = useState<KBChunk[] | null>(null);
  const [latency, setLatency] = useState(0);

  const run = async () => {
    if (!query.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      const r = await toolKbSearch({ query, scheme: scheme || null, k: 6 });
      setChunks(r.chunks);
      setLatency(r.latency_ms);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Search failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4">
      <Card className="surface-raised border-blue-100">
        <CardContent className="pt-5">
          <form
            className="flex flex-col gap-3 sm:flex-row sm:items-end"
            onSubmit={(e) => {
              e.preventDefault();
              run();
            }}
          >
            <label className="flex-1 text-sm">
              <span className="mb-1 block text-xs font-medium text-muted-foreground">Query</span>
              <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Ask about any scheme rule or benefit…" />
            </label>
            <div className="w-full sm:w-44">
              <SelectField
                label="Scheme filter"
                value={scheme}
                onChange={setScheme}
                options={enums?.kb_schemes || []}
                allowEmpty="all schemes"
              />
            </div>
            <Button type="submit" disabled={busy || !query.trim()} className="gradient-ministry sm:mb-0">
              {busy ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />} Search
            </Button>
          </form>
        </CardContent>
      </Card>

      {error && <div className="text-sm text-destructive">{error}</div>}

      {chunks && (
        <div className="space-y-3">
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            {chunks.length} passages <LatencyBadge ms={latency} />
          </div>
          {chunks.map((c, i) => (
            <Card key={i} className="ui-lift overflow-hidden border-l-4 border-l-ministry/60">
              <CardContent className="pt-4">
                <div className="mb-2 flex flex-wrap items-center gap-2">
                  <Badge variant="accent" className="capitalize">{c.scheme}</Badge>
                  <span className="text-xs font-medium text-ministry">{c.citation}</span>
                  <Badge variant="muted">score {c.score.toFixed(3)}</Badge>
                </div>
                <p className="whitespace-pre-wrap text-sm leading-relaxed text-muted-foreground">{c.text}</p>
              </CardContent>
            </Card>
          ))}
          {chunks.length === 0 && (
            <div className="dot-pattern grid min-h-52 place-items-center rounded-2xl border border-dashed border-blue-200 bg-white/70 px-8 text-center">
              <div>
                <div className="mx-auto grid h-12 w-12 place-items-center rounded-2xl bg-blue-50 text-ministry">
                  <Search className="h-5 w-5" />
                </div>
                <h3 className="mt-3 font-display text-sm font-semibold text-foreground">
                  No passages matched
                </h3>
                <p className="mt-1 text-xs text-muted-foreground">
                  Try a broader phrase or search across all schemes.
                </p>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Eligibility — form generated from the backend's Pydantic JSON Schema
// --------------------------------------------------------------------------- //
type FieldSpec = {
  name: string;
  title: string;
  kind: "enum" | "int" | "bool" | "str";
  options?: string[];
  required: boolean;
  description?: string;
};

const FIELD_LABELS: Record<string, string> = {
  beneficiary_type: "Who is the benefit for?",
  age_years: "Age",
  pregnancy_week: "Current pregnancy week",
  months_postpartum: "Months since delivery",
  child_order: "Birth order of this child",
  second_child_is_girl: "Is the second child a girl?",
  child_age_months: "Child age in months",
  is_awc_enrolled: "Enrolled at an Anganwadi Centre?",
  income_band: "Household income category",
  annual_family_income: "Annual family income (₹)",
  nfsa_member: "NFSA card holder?",
  caste_category: "Social category",
  is_disabled: "Person with benchmark disability?",
  family_in_crisis: "Is the family currently in crisis?",
  district: "District",
  is_aspirational_district: "Aspirational or North-Eastern district?",
};

const BENEFICIARY_FIELDS: Record<string, string[]> = {
  "pregnant woman": [
    "age_years",
    "pregnancy_week",
    "child_order",
    "second_child_is_girl",
    "income_band",
    "annual_family_income",
    "nfsa_member",
    "caste_category",
    "is_disabled",
    "district",
  ],
  "lactating mother": [
    "age_years",
    "months_postpartum",
    "child_order",
    "second_child_is_girl",
    "income_band",
    "annual_family_income",
    "nfsa_member",
    "caste_category",
    "is_disabled",
    "district",
  ],
  child: ["child_age_months", "is_awc_enrolled", "family_in_crisis", "district"],
  "adolescent girl": [
    "age_years",
    "is_awc_enrolled",
    "income_band",
    "district",
    "is_aspirational_district",
  ],
  family: [
    "income_band",
    "annual_family_income",
    "nfsa_member",
    "caste_category",
    "is_disabled",
    "family_in_crisis",
    "district",
  ],
};

const FIELD_GROUPS = [
  {
    id: "beneficiary",
    title: "Beneficiary details",
    description: "Tell us who needs support and the details relevant to their life stage.",
    fields: [
      "beneficiary_type",
      "age_years",
      "pregnancy_week",
      "months_postpartum",
      "child_order",
      "second_child_is_girl",
      "child_age_months",
    ],
  },
  {
    id: "household",
    title: "Household and support",
    description: "These details help match category-based and income-based scheme rules.",
    fields: [
      "is_awc_enrolled",
      "income_band",
      "annual_family_income",
      "nfsa_member",
      "caste_category",
      "is_disabled",
      "family_in_crisis",
    ],
  },
  {
    id: "location",
    title: "Location",
    description: "Some services and benefits depend on district coverage.",
    fields: ["district", "is_aspirational_district"],
  },
];

function humanizeFieldName(name: string) {
  return name
    .replaceAll("_", " ")
    .replace(/\bawc\b/i, "Anganwadi Centre")
    .replace(/\bnfsa\b/i, "NFSA")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function parseEligibilitySchema(schema: Record<string, any> | undefined): FieldSpec[] {
  if (!schema?.properties) return [];
  const defs = (schema.$defs || {}) as Record<string, any>;
  const required: string[] = schema.required || [];
  const resolve = (node: any): any => {
    if (!node) return node;
    if (node.$ref) return resolve(defs[String(node.$ref).split("/").pop() || ""]);
    if (Array.isArray(node.allOf) && node.allOf.length === 1) return resolve(node.allOf[0]);
    if (Array.isArray(node.anyOf)) {
      const nonNull = node.anyOf.filter((n: any) => n.type !== "null");
      if (nonNull.length === 1) return resolve(nonNull[0]);
    }
    return node;
  };
  return Object.entries(schema.properties as Record<string, any>).map(([name, raw]) => {
    const node = resolve(raw) || {};
    const kind: FieldSpec["kind"] = node.enum
      ? "enum"
      : node.type === "integer"
        ? "int"
        : node.type === "boolean"
          ? "bool"
          : "str";
    return {
      name,
      title:
        FIELD_LABELS[name] ||
        ((raw.title as string)?.includes("_") ? humanizeFieldName(name) : raw.title) ||
        humanizeFieldName(name),
      kind,
      options: node.enum as string[] | undefined,
      required: required.includes(name),
      description: raw.description as string | undefined,
    };
  });
}

function EligibilityPanel({ schema }: { schema?: Record<string, unknown> }) {
  const fields = useMemo(() => parseEligibilitySchema(schema as Record<string, any>), [schema]);
  const [values, setValues] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<EligibilityResult | null>(null);

  const set = (name: string, v: string) => setValues((s) => ({ ...s, [name]: v }));
  const beneficiaryType = values["beneficiary_type"] || "";
  const relevantNames = new Set([
    "beneficiary_type",
    ...(BENEFICIARY_FIELDS[beneficiaryType] || []),
  ]);
  const visibleFields = fields.filter((field) => relevantNames.has(field.name));
  const groupedFields = FIELD_GROUPS.map((group) => ({
    ...group,
    fields: visibleFields.filter((field) => group.fields.includes(field.name)),
  })).filter((group) => group.fields.length > 0);

  const run = async () => {
    if (busy) return;
    const body: Record<string, unknown> = {};
    for (const f of visibleFields) {
      const raw = values[f.name];
      if (raw === undefined || raw === "") continue;
      body[f.name] =
        f.kind === "int" ? Number(raw) : f.kind === "bool" ? raw === "true" : raw;
    }
    setBusy(true);
    setError(null);
    try {
      setResult(await toolEligibility(body));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Eligibility check failed");
    } finally {
      setBusy(false);
    }
  };

  if (!fields.length) {
    return <div className="text-sm text-muted-foreground">Loading form schema…</div>;
  }

  return (
    <div className="grid gap-5 lg:grid-cols-[460px_1fr]">
      <Card className="surface-raised self-start border-blue-100 lg:sticky lg:top-24">
        <CardContent className="pt-5">
          <div className="mb-5 flex items-start justify-between gap-3 border-b border-border pb-4">
            <div>
              <h2 className="font-semibold text-foreground">Check scheme eligibility</h2>
              <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                Questions adapt to the selected beneficiary. Leave optional details blank if unknown.
              </p>
            </div>
            <div className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-ministry-soft text-ministry">
              <ClipboardCheck className="h-4 w-4" />
            </div>
          </div>
          <form
            className="space-y-5"
            onSubmit={(e) => {
              e.preventDefault();
              run();
            }}
          >
            {groupedFields.map((group) => (
              <fieldset key={group.id} className="space-y-3">
                <legend className="text-sm font-semibold text-foreground">{group.title}</legend>
                <p className="-mt-1 text-xs leading-relaxed text-muted-foreground">
                  {group.description}
                </p>
                <div className="grid gap-3">
                  {group.fields.map((field) => (
                    <EligibilityField
                      key={field.name}
                      field={field}
                      value={values[field.name] ?? ""}
                      onChange={(value) => set(field.name, value)}
                    />
                  ))}
                </div>
              </fieldset>
            ))}
            <Button type="submit" disabled={busy || !values["beneficiary_type"]} className="w-full gradient-ministry">
              {busy ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Landmark className="h-4 w-4" />} Check eligibility
            </Button>
          </form>
        </CardContent>
      </Card>

      <div className="space-y-3">
        {error && <div role="alert" className="rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">{error}</div>}
        {result && (
          <>
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              Checked: {result.checked_schemes.join(", ") || "—"} <LatencyBadge ms={result.latency_ms} />
            </div>
            {(["eligible", "uncertain", "ineligible"] as const).map((bucket) =>
              result[bucket].map((r) => <RuleCard key={bucket + r.scheme} r={r} bucket={bucket} />)
            )}
            {!result.eligible.length && !result.uncertain.length && !result.ineligible.length && (
              <div className="text-sm text-muted-foreground">No rules matched the given facts.</div>
            )}
          </>
        )}
        {!result && !error && (
          <div className="dot-pattern surface-raised fade-up grid min-h-[280px] place-items-center rounded-2xl border border-dashed border-blue-200 bg-white/70 px-8 text-center">
            <div className="max-w-sm">
              <div className="hero-halo mx-auto grid h-14 w-14 place-items-center rounded-2xl text-ministry shadow-sm">
                <Landmark className="h-5 w-5" />
              </div>
              <h3 className="mt-4 font-display font-semibold text-foreground">Your eligibility results will appear here</h3>
              <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                Select a beneficiary, add the details you know, and run the check. Every result includes its reason and official source.
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function EligibilityField({
  field,
  value,
  onChange,
}: {
  field: FieldSpec;
  value: string;
  onChange: (value: string) => void;
}) {
  const label = field.title + (field.required ? " *" : "");

  if (field.kind === "bool") {
    return (
      <div>
        <div className="mb-1.5 text-xs font-medium text-foreground">{label}</div>
        <div className="inline-flex rounded-lg border border-input bg-secondary/60 p-1">
          {[
            { value: "", label: "Not sure" },
            { value: "true", label: "Yes" },
            { value: "false", label: "No" },
          ].map((option) => (
            <button
              key={option.label}
              type="button"
              aria-pressed={value === option.value}
              onClick={() => onChange(option.value)}
              className={cn(
                "rounded-md px-3 py-1.5 text-xs font-medium transition-colors",
                value === option.value
                  ? "bg-white text-primary shadow-sm"
                  : "text-muted-foreground hover:text-foreground"
              )}
            >
              {option.label}
            </button>
          ))}
        </div>
        {field.description && (
          <p className="mt-1.5 flex gap-1.5 text-xs leading-relaxed text-muted-foreground">
            <Info className="mt-0.5 h-3 w-3 shrink-0" />
            {field.description}
          </p>
        )}
      </div>
    );
  }

  return (
    <div>
      {field.kind === "enum" ? (
        <SelectField
          label={label}
          value={value}
          onChange={onChange}
          options={field.options || []}
          allowEmpty={field.required ? "Select an option…" : "Not specified"}
        />
      ) : (
        <label className="block text-sm">
          <span className="mb-1 block text-xs font-medium text-foreground">{label}</span>
          <Input
            type={field.kind === "int" ? "number" : "text"}
            min={field.kind === "int" ? 0 : undefined}
            value={value}
            onChange={(event) => onChange(event.target.value)}
          />
        </label>
      )}
      {field.description && (
        <p className="mt-1.5 flex gap-1.5 text-xs leading-relaxed text-muted-foreground">
          <Info className="mt-0.5 h-3 w-3 shrink-0" />
          {field.description}
        </p>
      )}
    </div>
  );
}

function RuleCard({ r, bucket }: { r: RuleResult; bucket: "eligible" | "uncertain" | "ineligible" }) {
  const surface =
    bucket === "eligible"
      ? "border-l-emerald-500 bg-gradient-to-r from-emerald-50/70 to-white"
      : bucket === "uncertain"
        ? "border-l-amber-500 bg-gradient-to-r from-amber-50/70 to-white"
        : "border-l-rose-500 bg-gradient-to-r from-rose-50/70 to-white";
  const iconSurface =
    bucket === "eligible"
      ? "bg-emerald-100"
      : bucket === "uncertain"
        ? "bg-amber-100"
        : "bg-rose-100";
  const icon =
    bucket === "eligible" ? (
      <CheckCircle2 className="h-4 w-4 text-emerald-600" />
    ) : bucket === "uncertain" ? (
      <CircleHelp className="h-4 w-4 text-amber-600" />
    ) : (
      <XCircle className="h-4 w-4 text-rose-600" />
    );
  return (
    <Card className={cn("fade-up overflow-hidden border-l-4", surface)}>
      <CardContent className="pt-4">
        <div className="mb-1.5 flex flex-wrap items-center gap-2">
          <span className={cn("grid h-8 w-8 place-items-center rounded-lg", iconSurface)}>
            {icon}
          </span>
          <span className="text-sm font-semibold">{r.scheme}</span>
          {r.amount && <Badge variant="accent">{r.amount}</Badge>}
          {r.instalments && <Badge variant="muted">{r.instalments}</Badge>}
        </div>
        {r.benefit_summary && <p className="text-sm text-muted-foreground">{r.benefit_summary}</p>}
        <p className="mt-1 text-sm">{r.reason}</p>
        {r.needs.length > 0 && (
          <p className="mt-1 text-xs text-amber-700">
            Needs: {r.needs.join(", ")}
          </p>
        )}
        <p className="mt-2 text-xs text-muted-foreground">Source: {r.source_doc}</p>
      </CardContent>
    </Card>
  );
}

// --------------------------------------------------------------------------- //
// Facility locator (geo)
// --------------------------------------------------------------------------- //
function GeoPanel({ enums }: { enums?: Record<string, string[]> }) {
  const [serviceType, setServiceType] = useState("AWC");
  const [district, setDistrict] = useState("Varanasi");
  const [state, setState] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resp, setResp] = useState<Awaited<ReturnType<typeof toolGeo>> | null>(null);

  const run = async () => {
    if (!district.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      setResp(await toolGeo({ service_type: serviceType, district, state: state || null, limit: 5 }));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Lookup failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4">
      <Card className="surface-raised border-blue-100">
        <CardContent className="pt-5">
          <form
            className="grid gap-3 sm:grid-cols-[170px_1fr_1fr_auto] sm:items-end"
            onSubmit={(e) => {
              e.preventDefault();
              run();
            }}
          >
            <SelectField
              label="Facility type"
              value={serviceType}
              onChange={setServiceType}
              options={enums?.geo_service_types || ["AWC", "OSC", "DCPU", "CWC"]}
            />
            <label className="text-sm">
              <span className="mb-1 block text-xs font-medium text-muted-foreground">District</span>
              <Input value={district} onChange={(e) => setDistrict(e.target.value)} />
            </label>
            <label className="text-sm">
              <span className="mb-1 block text-xs font-medium text-muted-foreground">State (optional fallback)</span>
              <Input value={state} onChange={(e) => setState(e.target.value)} />
            </label>
            <Button type="submit" disabled={busy || !district.trim()} className="gradient-ministry">
              {busy ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <MapPin className="h-4 w-4" />} Locate
            </Button>
          </form>
        </CardContent>
      </Card>

      {error && <div className="text-sm text-destructive">{error}</div>}

      {resp && (
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
            {resp.count} facilities
            {resp.district_matched && <Badge variant="accent">{resp.district_matched}</Badge>}
            <LatencyBadge ms={resp.latency_ms} />
          </div>
          {resp.note && <div className="text-sm text-amber-700">{resp.note}</div>}
          <div className="grid gap-3 md:grid-cols-2">
            {resp.facilities.map((f: Facility) => (
              <Card key={f.id} className="ui-lift overflow-hidden border-l-4 border-l-sky-500">
                <CardContent className="pt-4">
                  <div className="mb-1 flex items-center gap-2">
                    <Badge variant="accent">{f.type}</Badge>
                    <span className="text-sm font-semibold">{f.name}</span>
                  </div>
                  <p className="text-sm text-muted-foreground">{f.address}</p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {f.district}, {f.state}
                    {f.phone ? ` · ${f.phone}` : ""}
                    {f.hours ? ` · ${f.hours}` : ""}
                  </p>
                </CardContent>
              </Card>
            ))}
          </div>
          {resp.facilities.length === 0 && (
            <div className="dot-pattern grid min-h-52 place-items-center rounded-2xl border border-dashed border-blue-200 bg-white/70 text-center">
              <div>
                <div className="mx-auto grid h-12 w-12 place-items-center rounded-2xl bg-sky-50 text-sky-700">
                  <MapPin className="h-5 w-5" />
                </div>
                <h3 className="mt-3 font-display text-sm font-semibold">
                  No facilities found
                </h3>
                <p className="mt-1 text-xs text-muted-foreground">
                  Check the district spelling or add a state for a wider match.
                </p>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Helpline directory
// --------------------------------------------------------------------------- //
function HelplinePanel({ enums }: { enums?: Record<string, string[]> }) {
  const [category, setCategory] = useState("women_safety");
  const [scheme, setScheme] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resp, setResp] = useState<Awaited<ReturnType<typeof toolHelpline>> | null>(null);

  const run = async () => {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      setResp(await toolHelpline({ category, scheme: scheme || null }));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Lookup failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4">
      <Card className="surface-raised border-blue-100">
        <CardContent className="pt-5">
          <form
            className="grid gap-3 sm:grid-cols-[1fr_200px_auto] sm:items-end"
            onSubmit={(e) => {
              e.preventDefault();
              run();
            }}
          >
            <SelectField
              label="Situation category"
              value={category}
              onChange={setCategory}
              options={enums?.helpline_categories || []}
            />
            <SelectField
              label="Scheme hint"
              value={scheme}
              onChange={setScheme}
              options={enums?.helpline_schemes || []}
              allowEmpty="—"
            />
            <Button type="submit" disabled={busy} className="gradient-ministry">
              {busy ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Phone className="h-4 w-4" />} Look up
            </Button>
          </form>
        </CardContent>
      </Card>

      {error && <div className="text-sm text-destructive">{error}</div>}

      {resp && (
        <div className="space-y-3">
          <HelplineCard entry={resp.primary} primary />
          {resp.secondary.map((h) => (
            <HelplineCard key={h.id} entry={h} />
          ))}
          {resp.escalation_note && (
            <div className="rounded-lg border border-amber-300 bg-amber-50 px-4 py-2 text-sm text-amber-800">
              {resp.escalation_note}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function HelplineCard({ entry, primary = false }: { entry: HelplineEntry; primary?: boolean }) {
  return (
    <Card
      className={cn(
        "ui-lift overflow-hidden",
        primary
          ? "border-l-4 border-l-ministry bg-gradient-to-r from-blue-50/80 to-white shadow-md"
          : "border-l-4 border-l-slate-300",
      )}
    >
      <CardContent className="pt-4">
        <div className="flex flex-wrap items-center gap-3">
          <div className="grid h-12 w-16 place-items-center rounded-lg gradient-ministry text-lg font-bold text-white">
            {entry.number || "—"}
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <span className="text-sm font-semibold">{entry.name}</span>
              {primary && <Badge variant="accent">primary</Badge>}
              {entry.hours && <Badge variant="muted">{entry.hours}</Badge>}
            </div>
            <p className="mt-0.5 text-sm text-muted-foreground">{entry.when_to_call}</p>
            {entry.escalation_note && (
              <p className="mt-1 text-xs text-amber-700">{entry.escalation_note}</p>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
