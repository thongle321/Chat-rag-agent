import { computed, ref } from "vue";
import api, { getErrorMessage } from "../api/index.ts";

export interface Product {
	id: string;
	name: string;
	description?: string;
	price?: number | null;
	currency?: string | null;
	image_url?: string | null;
	product_url?: string | null;
	category?: string | null;
	stock?: number | null;
	source?: string | null;
}

export interface ProductForm {
	name: string;
	description: string;
	price: number | null;
	currency: string;
	image_url: string;
	product_url: string;
	category: string;
	stock: number;
}

export function blankProductForm(): ProductForm {
	return {
		name: "",
		description: "",
		price: null,
		currency: "USD",
		image_url: "",
		product_url: "",
		category: "",
		stock: 0,
	};
}

// Local catalog: list + client filter/sort + manual CRUD + CSV import.
export function useProductCatalog() {
	const toast = useToast();
	const products = ref<Product[]>([]);
	const loading = ref(false);
	const loadError = ref("");
	const saving = ref(false);
	const importing = ref(false);
	const query = ref("");
	const sortBy = ref<keyof Product>("name");
	const sortDir = ref<"asc" | "desc">("asc");

	const filtered = computed(() => {
		const list = products.value.slice();
		const q = query.value.trim().toLowerCase();
		const matches = q
			? list.filter((p) => (p.name || "").toLowerCase().includes(q) || (p.category || "").toLowerCase().includes(q))
			: list;
		matches.sort((a, b) => {
			const aStr = (a[sortBy.value] ?? "").toString().toLowerCase();
			const bStr = (b[sortBy.value] ?? "").toString().toLowerCase();
			const cmp = aStr < bStr ? -1 : aStr > bStr ? 1 : 0;
			return sortDir.value === "asc" ? cmp : -cmp;
		});
		return matches;
	});

	function toggleSort(field: keyof Product) {
		if (sortBy.value === field) {
			sortDir.value = sortDir.value === "asc" ? "desc" : "asc";
		} else {
			sortBy.value = field;
			sortDir.value = "asc";
		}
	}

	async function load() {
		loading.value = true;
		loadError.value = "";
		try {
			const { data } = await api.get("/products/");
			products.value = data.products ?? [];
		} catch (err: unknown) {
			loadError.value = getErrorMessage(err);
			products.value = [];
		} finally {
			loading.value = false;
		}
	}

	async function saveProduct(editing: Product | null, form: ProductForm): Promise<boolean> {
		if (!form.name.trim()) return false;
		saving.value = true;
		const payload = {
			name: form.name.trim(),
			description: form.description.trim() || "",
			price: form.price ?? null,
			currency: form.currency.trim() || "USD",
			image_url: form.image_url.trim() || "",
			product_url: form.product_url.trim() || "",
			category: form.category.trim() || "",
			stock: form.stock ?? 0,
		};
		try {
			if (editing) {
				await api.put(`/products/${editing.id}`, payload);
			} else {
				await api.post("/products/", payload);
			}
			await load();
			toast.add({ color: "success", title: "Saved", timeout: 3000 });
			return true;
		} catch (err: unknown) {
			toast.add({ color: "error", description: getErrorMessage(err), title: "Save failed" });
			return false;
		} finally {
			saving.value = false;
		}
	}

	async function removeProduct(id: string) {
		await api.delete(`/products/${id}`);
		await load();
	}

	async function importCsv(file: File) {
		importing.value = true;
		try {
			const fd = new FormData();
			fd.append("file", file);
			const { data } = await api.post("/products/import-csv", fd);
			await load();
			toast.add({
				color: (data.imported ?? 0) > 0 ? "success" : "warning",
				description:
					`Imported ${data.imported ?? 0} products` +
					(data.skipped ? `, skipped ${data.skipped} rows missing name/price.` : "."),
				icon: "i-lucide-file-spreadsheet",
				timeout: 6000,
				title: "CSV import",
			});
		} finally {
			importing.value = false;
		}
	}

	return {
		filtered,
		importCsv,
		importing,
		load,
		loadError,
		loading,
		products,
		query,
		removeProduct,
		saveProduct,
		saving,
		sortBy,
		sortDir,
		toggleSort,
	};
}
