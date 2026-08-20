/**
 * Customers and products — the things a project is *about*.
 *
 * Both were creatable through the API and nowhere in the app, so the first
 * real project could not be created at all: choosing a customer offered an
 * empty list and there was no way to add one without a developer. A system
 * whose very first step needs a developer is not usable by the department that
 * owns it.
 *
 * Products carry more weight than they look: a product is what decides which
 * standard design releases a project produces, so adding one here without
 * defining its DSQ list leaves a product that generates nothing. The screen
 * says so rather than letting that be discovered later.
 */

import { Boxes, Building2, Pencil, Plus } from "lucide-react";
import { useMemo, useState } from "react";

import { Field, FormError, Select, TextArea, TextInput } from "@/components/ui/form";
import { Modal } from "@/components/ui/Modal";
import { ResponsiveTable } from "@/components/ui/ResponsiveTable";
import {
  Card,
  EmptyState,
  ErrorState,
  InlineAlert,
  PageHeader,
  SkeletonRows,
  Spinner,
} from "@/components/ui/primitives";
import {
  useCreateCustomer,
  useCreateProduct,
  useCustomers,
  useProductFamilies,
  useProducts,
  useUpdateCustomer,
  useUpdateProduct,
} from "@/hooks/queries";
import { DASH } from "@/lib/format";
import { P, useAuth } from "@/store/auth";
import type { Customer, Product } from "@/types/api";

type Tab = "customers" | "products";

/** SIEGER PARKING → SIEGER-PARKING, which is what the code column expects. */
function suggestCode(name: string): string {
  return name
    .trim()
    .toUpperCase()
    .replace(/[^A-Z0-9]+/g, "-")
    .replace(/^-|-$/g, "")
    .slice(0, 40);
}

function CustomerModal({
  customer,
  onClose,
}: {
  customer?: Customer;
  onClose: () => void;
}) {
  const editing = Boolean(customer);
  const create = useCreateCustomer();
  const update = useUpdateCustomer(customer?.id ?? "");
  const pending = create.isPending || update.isPending;

  const [name, setName] = useState(customer?.name ?? "");
  const [code, setCode] = useState(customer?.customer_code ?? "");
  const [codeTouched, setCodeTouched] = useState(editing);
  const [industry, setIndustry] = useState(customer?.industry ?? "");
  const [country, setCountry] = useState(customer?.country ?? "India");
  const [contactName, setContactName] = useState(customer?.contact_name ?? "");
  const [contactEmail, setContactEmail] = useState(customer?.contact_email ?? "");
  const [contactPhone, setContactPhone] = useState(customer?.contact_phone ?? "");

  const ready = name.trim().length > 0 && code.trim().length > 0;

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    if (!ready) return;

    const body = {
      name: name.trim(),
      industry: industry.trim() || null,
      country: country.trim() || null,
      contact_name: contactName.trim() || null,
      // An empty string fails email validation; absent is what "unknown" means.
      contact_email: contactEmail.trim() || null,
      contact_phone: contactPhone.trim() || null,
    };

    if (editing) {
      update.mutate(body, { onSuccess: onClose });
      return;
    }
    create.mutate({ ...body, customer_code: code.trim() }, { onSuccess: onClose });
  };

  return (
    <Modal
      open
      onClose={onClose}
      size="md"
      title={editing ? `Edit ${customer?.name}` : "Add a customer"}
      footer={
        <>
          <button type="button" className="btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button
            type="submit"
            form="customer-form"
            className="btn-primary"
            disabled={!ready || pending}
          >
            {pending && <Spinner className="h-4 w-4" />}
            {editing ? "Save" : "Add"}
          </button>
        </>
      }
    >
      <form id="customer-form" onSubmit={submit} className="space-y-3">
        <FormError error={create.error ?? update.error} />

        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Name">
            <TextInput
              value={name}
              onChange={(event) => {
                setName(event.target.value);
                if (!codeTouched && !editing) setCode(suggestCode(event.target.value));
              }}
              placeholder="Ganga Medical Trust"
              required
            />
          </Field>

          <Field
            label="Customer code"
            hint={editing ? "Fixed once created." : "Short, unique, used on documents."}
          >
            <TextInput
              value={code}
              onChange={(event) => {
                setCodeTouched(true);
                setCode(event.target.value.toUpperCase());
              }}
              placeholder="GANGA-MED"
              disabled={editing}
              required
            />
          </Field>
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Industry">
            <TextInput
              value={industry}
              onChange={(event) => setIndustry(event.target.value)}
              placeholder="Healthcare"
            />
          </Field>
          <Field label="Country">
            <TextInput
              value={country}
              onChange={(event) => setCountry(event.target.value)}
            />
          </Field>
        </div>

        <Field label="Contact person">
          <TextInput
            value={contactName}
            onChange={(event) => setContactName(event.target.value)}
            placeholder="Procurement lead"
          />
        </Field>

        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Contact email">
            <TextInput
              type="email"
              value={contactEmail}
              onChange={(event) => setContactEmail(event.target.value)}
            />
          </Field>
          <Field label="Contact phone">
            <TextInput
              value={contactPhone}
              onChange={(event) => setContactPhone(event.target.value)}
            />
          </Field>
        </div>
      </form>
    </Modal>
  );
}

function ProductModal({ product, onClose }: { product?: Product; onClose: () => void }) {
  const editing = Boolean(product);
  const families = useProductFamilies();
  const create = useCreateProduct();
  const update = useUpdateProduct(product?.id ?? "");
  const pending = create.isPending || update.isPending;

  const [name, setName] = useState(product?.name ?? "");
  const [familyId, setFamilyId] = useState(product?.product_family_id ?? "");
  const [description, setDescription] = useState(product?.description ?? "");

  const ready = name.trim().length > 0;

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    if (!ready) return;
    const body = {
      name: name.trim(),
      product_family_id: familyId || null,
      description: description.trim() || null,
    };
    if (editing) {
      update.mutate(body, { onSuccess: onClose });
      return;
    }
    create.mutate(body, { onSuccess: onClose });
  };

  return (
    <Modal
      open
      onClose={onClose}
      size="md"
      title={editing ? `Edit ${product?.name}` : "Add a product"}
      footer={
        <>
          <button type="button" className="btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button
            type="submit"
            form="product-form"
            className="btn-primary"
            disabled={!ready || pending}
          >
            {pending && <Spinner className="h-4 w-4" />}
            {editing ? "Save" : "Add"}
          </button>
        </>
      }
    >
      <form id="product-form" onSubmit={submit} className="space-y-3">
        <FormError error={create.error ?? update.error} />

        <Field label="Name">
          <TextInput
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="Puzzle"
            required
          />
        </Field>

        <Field label="Family" hint="Groups products for reporting.">
          <Select
            value={familyId ?? ""}
            onChange={(event) => setFamilyId(event.target.value)}
            options={[
              { value: "", label: "None" },
              ...(families.data ?? []).map((f) => ({ value: f.id, label: f.name })),
            ]}
          />
        </Field>

        <Field label="Description">
          <TextArea
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            rows={2}
          />
        </Field>

        {!editing && (
          <InlineAlert tone="info">
            A new product has no standard design releases yet, so projects using
            it will not generate any. Its DSQ list is defined in the seed data —
            ask whoever maintains the system to add it.
          </InlineAlert>
        )}
      </form>
    </Modal>
  );
}

export default function Catalog() {
  const can = useAuth((s) => s.can);
  const [tab, setTab] = useState<Tab>("customers");
  const [editingCustomer, setEditingCustomer] = useState<Customer | null>(null);
  const [editingProduct, setEditingProduct] = useState<Product | null>(null);
  const [adding, setAdding] = useState(false);

  const customers = useCustomers({ page_size: 200, active_only: false });
  const products = useProducts();

  const canAddCustomer = can(P.projectCreate);
  const canAddProduct = can(P.settingsManage);
  const canAdd = tab === "customers" ? canAddCustomer : canAddProduct;

  const customerRows = useMemo(
    () => customers.data?.items ?? [],
    [customers.data],
  );

  return (
    <div className="space-y-4">
      <PageHeader
        title="Catalogue"
        subtitle="Who the work is for, and what it is."
        actions={
          canAdd && (
            <button type="button" className="btn-primary" onClick={() => setAdding(true)}>
              <Plus className="h-4 w-4" />
              {tab === "customers" ? "Add a customer" : "Add a product"}
            </button>
          )
        }
      />

      <div
        className="inline-flex rounded-lg border border-ink-200 bg-white p-0.5"
        role="tablist"
      >
        {(
          [
            { key: "customers", label: "Customers", icon: Building2 },
            { key: "products", label: "Products", icon: Boxes },
          ] as const
        ).map((entry) => (
          <button
            key={entry.key}
            type="button"
            role="tab"
            aria-selected={tab === entry.key}
            className={
              tab === entry.key
                ? "flex items-center gap-1.5 rounded-md bg-signal-600 px-3 py-1.5 text-sm font-medium text-white"
                : "flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm text-ink-600 hover:bg-cream-100"
            }
            onClick={() => setTab(entry.key)}
          >
            <entry.icon className="h-4 w-4" />
            {entry.label}
          </button>
        ))}
      </div>

      {tab === "customers" && (
        <>
          {customers.isError && <ErrorState onRetry={() => void customers.refetch()} />}
          {customers.isLoading && <SkeletonRows rows={4} cols={3} />}
          {customers.data &&
            (customerRows.length === 0 ? (
              <Card>
                <EmptyState
                  title="No customers yet"
                  description="A project belongs to a customer, so this is the first thing to fill in."
                  icon={<Building2 className="h-6 w-6" />}
                  action={
                    canAddCustomer && (
                      <button
                        type="button"
                        className="btn-primary"
                        onClick={() => setAdding(true)}
                      >
                        Add the first customer
                      </button>
                    )
                  }
                />
              </Card>
            ) : (
              <Card bodyClassName="">
                <ResponsiveTable
                  rows={customerRows}
                  rowKey={(row) => row.id}
                  minWidth="48rem"
                  columns={[
                    {
                      key: "name",
                      mobile: "primary",
                      header: "Customer",
                      cell: (row) => (
                        <span className="font-medium text-ink-900">{row.name}</span>
                      ),
                    },
                    {
                      key: "code",
                      mobile: "meta",
                      header: "Code",
                      cell: (row) => (
                        <span className="font-mono text-xs text-ink-600">
                          {row.customer_code}
                        </span>
                      ),
                    },
                    {
                      key: "industry",
                      mobile: "field",
                      header: "Industry",
                      cell: (row) => row.industry ?? DASH,
                    },
                    {
                      key: "country",
                      mobile: "field",
                      header: "Country",
                      cell: (row) => row.country ?? DASH,
                    },
                    {
                      key: "contact",
                      mobile: "field",
                      header: "Contact",
                      cell: (row) => row.contact_name ?? DASH,
                    },
                    {
                      key: "actions",
                      align: "right",
                      mobile: "field",
                      header: "",
                      cell: (row) =>
                        canAddCustomer && (
                          <button
                            type="button"
                            className="btn-ghost px-1.5"
                            aria-label={`Edit ${row.name}`}
                            onClick={() => setEditingCustomer(row)}
                          >
                            <Pencil className="h-4 w-4" />
                          </button>
                        ),
                    },
                  ]}
                />
              </Card>
            ))}
        </>
      )}

      {tab === "products" && (
        <>
          {products.isError && <ErrorState onRetry={() => void products.refetch()} />}
          {products.isLoading && <SkeletonRows rows={4} cols={3} />}
          {products.data && (
            <Card bodyClassName="">
              <ResponsiveTable
                rows={products.data}
                rowKey={(row) => row.id}
                minWidth="42rem"
                columns={[
                  {
                    key: "name",
                    mobile: "primary",
                    header: "Product",
                    cell: (row) => (
                      <span className="font-medium text-ink-900">{row.name}</span>
                    ),
                  },
                  {
                    key: "family",
                    mobile: "meta",
                    header: "Family",
                    cell: (row) => row.product_family_name ?? DASH,
                  },
                  {
                    key: "description",
                    mobile: "field",
                    header: "Description",
                    cell: (row) => row.description ?? DASH,
                  },
                  {
                    key: "actions",
                    align: "right",
                    mobile: "field",
                    header: "",
                    cell: (row) =>
                      canAddProduct && (
                        <button
                          type="button"
                          className="btn-ghost px-1.5"
                          aria-label={`Edit ${row.name}`}
                          onClick={() => setEditingProduct(row)}
                        >
                          <Pencil className="h-4 w-4" />
                        </button>
                      ),
                  },
                ]}
              />
            </Card>
          )}
        </>
      )}

      {adding && tab === "customers" && (
        <CustomerModal onClose={() => setAdding(false)} />
      )}
      {adding && tab === "products" && <ProductModal onClose={() => setAdding(false)} />}
      {editingCustomer && (
        <CustomerModal
          customer={editingCustomer}
          onClose={() => setEditingCustomer(null)}
        />
      )}
      {editingProduct && (
        <ProductModal product={editingProduct} onClose={() => setEditingProduct(null)} />
      )}
    </div>
  );
}
