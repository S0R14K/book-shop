document.addEventListener("DOMContentLoaded", () => {
    loadBookEnrichment();

    const currencySelect = document.getElementById("currency-select");
    const convertedTotalField = document.getElementById("converted-total");
    const totalField = document.getElementById("total_eur");

    if (!currencySelect || !convertedTotalField || !totalField) {
        return;
    }

    const eurTotal = Number.parseFloat(totalField.dataset.total || "0");

    currencySelect.addEventListener("change", async () => {
        const selectedCurrency = currencySelect.value;
        convertedTotalField.textContent = "Loading...";

        try {
            const response = await fetch(
                `/api/convert?to=${encodeURIComponent(selectedCurrency)}&amount=${encodeURIComponent(eurTotal)}`
            );
            const data = await response.json();

            if (!response.ok || data.error) {
                convertedTotalField.textContent = data.error || "Conversion unavailable.";
                return;
            }

            convertedTotalField.textContent = `${data.total_converted} ${data.to}`;
        } catch (error) {
            convertedTotalField.textContent = "Conversion unavailable.";
        }
    });
});

async function loadBookEnrichment() {
    const panel = document.getElementById("book-enrichment");
    if (!panel) {
        return;
    }

    const source = document.getElementById("book-enrichment-source");
    const facts = document.getElementById("book-enrichment-facts");
    const description = document.getElementById("book-enrichment-description");

    try {
        const response = await fetch(panel.dataset.apiUrl);
        const payload = await response.json();

        if (!response.ok || payload.error || !payload.book) {
            source.textContent = "Unavailable";
            facts.innerHTML = "";
            const message = document.createElement("p");
            message.className = "muted";
            message.textContent = payload.error || "No external metadata match found right now.";
            facts.appendChild(message);
            description.textContent = "";
            return;
        }

        const book = payload.book;
        source.textContent = `${book.api_provider}${book.api_cached ? " cache" : " live"}`;
        facts.innerHTML = "";

        addFact(facts, "Authors", book.authors);
        addFact(facts, "First published", book.published_year);
        addFact(facts, "External ISBN", book.isbn);

        if (book.source_url) {
            const paragraph = document.createElement("p");
            const link = document.createElement("a");
            link.className = "text-link";
            link.href = book.source_url;
            link.target = "_blank";
            link.rel = "noopener";
            link.textContent = "View source record";
            paragraph.appendChild(link);
            facts.appendChild(paragraph);
        }

        description.textContent = book.description || "The external API returned metadata but no extra description for this title.";
    } catch (error) {
        source.textContent = "Unavailable";
        facts.innerHTML = "";
        const message = document.createElement("p");
        message.className = "muted";
        message.textContent = "External metadata is taking too long to load. The local book record is still available.";
        facts.appendChild(message);
        description.textContent = "";
    }
}

function addFact(container, label, value) {
    if (!value) {
        return;
    }
    const paragraph = document.createElement("p");
    const strong = document.createElement("strong");
    strong.textContent = `${label}: `;
    paragraph.appendChild(strong);
    paragraph.appendChild(document.createTextNode(value));
    container.appendChild(paragraph);
}
