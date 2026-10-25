// Keep one sidebar folder open. Pages and routes stay the same.
function moduleName() {
	const sidebar = document.querySelector(".body-sidebar");
	return sidebar?.getAttribute("data-title") || "";
}

function nestedOf(section) {
	return section.querySelector(":scope > .nested-container");
}

function isOpen(section) {
	const nested = nestedOf(section);
	return Boolean(nested && !nested.classList.contains("hidden"));
}

function remember(section, collapsed) {
	const label = section.getAttribute("item-name") || section.getAttribute("data-id");
	const module = moduleName();
	if (!label || !module) return;
	let state = {};
	try {
		state = JSON.parse(localStorage.getItem("section-breaks-state") || "{}");
	} catch {
		state = {};
	}
	if (!state[module]) state[module] = {};
	state[module][label] = collapsed;
	localStorage.setItem("section-breaks-state", JSON.stringify(state));
}

function closeSection(section) {
	if (!isOpen(section)) return;
	const nested = nestedOf(section);
	nested.classList.add("hidden");
	const icon = section.querySelector(":scope > .standard-sidebar-item .drop-icon use");
	if (icon) {
		icon.setAttribute("href", "#icon-chevron-right");
		icon.setAttribute("xlink:href", "#icon-chevron-right");
	}
	const drop = section.querySelector(":scope > .standard-sidebar-item .drop-icon");
	if (drop) {
		drop.setAttribute("data-state", "closed");
		drop.setAttribute("aria-expanded", "false");
	}
	remember(section, true);
}

function sections() {
	return [...document.querySelectorAll(".body-sidebar .sidebar-items > .section-item")];
}

function keepOneOpen(clicked) {
	const rows = sections();
	let keeper = clicked && isOpen(clicked) ? clicked : null;
	if (!keeper && !clicked) {
		keeper = rows.find((section) => section.querySelector(".active-sidebar")) || null;
	}
	rows.forEach((section) => {
		if (section !== keeper) closeSection(section);
	});
	if (keeper) remember(keeper, false);
}

function startFolderAccordion() {
	if (window.__erpFolderAccordion) return;
	window.__erpFolderAccordion = true;

	document.addEventListener("click", (event) => {
		const row = event.target.closest(
			".body-sidebar .sidebar-items > .section-item > .standard-sidebar-item"
		);
		if (!row?.parentElement) return;
		const section = row.parentElement;
		window.setTimeout(() => keepOneOpen(section), 0);
	});

	$(document).on("sidebar_setup", () => window.setTimeout(() => keepOneOpen(), 0));
	if (frappe.router) {
		frappe.router.on("change", () => window.setTimeout(() => keepOneOpen(), 50));
	}
	window.setTimeout(() => keepOneOpen(), 0);
	window.setTimeout(() => keepOneOpen(), 300);
}

frappe.ready(startFolderAccordion);
