function computeLineTotal(row) {
  const quantity = parseFloat(row.querySelector('[name="quantity[]"]').value) || 0;
  const price = parseFloat(row.querySelector('[name="price[]"]').value) || 0;
  const netPriceInput = row.querySelector('[name="net_price[]"]');
  const discountInput = row.querySelector('[name="discount[]"]');
  const discountPercentInput = row.querySelector('[name="discount_percent[]"]');
  const hasNetPrice = netPriceInput.value !== '';
  const netPrice = hasNetPrice ? (parseFloat(netPriceInput.value) || 0) : null;
  const discount = parseFloat(discountInput.value) || 0;
  const discountPercent = parseFloat(discountPercentInput.value) || 0;
  let unitPrice = price;
  if (hasNetPrice) {
    unitPrice = netPrice;
  } else if (discount > 0) {
    unitPrice = price - discount;
  } else if (discountPercent > 0) {
    unitPrice = price * (1 - (discountPercent / 100));
  }
  const total = quantity * unitPrice;
  row.querySelector('[name="line_total[]"]').value = total.toFixed(2);
  return total;
}

function refreshTicketTotal() {
  const rows = Array.from(document.querySelectorAll('.item-row'));
  const total = rows.reduce((sum, row) => sum + computeLineTotal(row), 0);
  const totalNode = document.getElementById('ticket-total');
  if (totalNode) {
    totalNode.textContent = `${total.toFixed(2)} €`;
  }
}

function bindRow(row) {
  row.querySelectorAll('input').forEach((input) => {
    input.addEventListener('input', refreshTicketTotal);
    input.addEventListener('change', refreshTicketTotal);
  });
  row.querySelector('.remove-row').addEventListener('click', () => {
    const rows = document.querySelectorAll('.item-row');
    if (rows.length > 1) {
      row.remove();
      refreshTicketTotal();
    }
  });
}

function bindSuggestions(scope = document) {
  scope.querySelectorAll('.suggestion-input[list]').forEach((input) => {
    if (input.dataset.suggestionBound === 'true') {
      return;
    }
    input.dataset.suggestionBound = 'true';
    const showSuggestions = () => {
      if (typeof input.showPicker === 'function') {
        try {
          input.showPicker();
        } catch (_error) {
          // Some browsers block showPicker without a direct user gesture.
        }
      }
    };
    input.addEventListener('focus', showSuggestions);
    input.addEventListener('click', showSuggestions);
  });
}

function addRow(item = null, { focusArticle = true } = {}) {
  const template = document.getElementById('item-row-template');
  const container = document.getElementById('items-container');
  const row = template.content.firstElementChild.cloneNode(true);
  container.appendChild(row);
  if (item) {
    row.querySelector('[name="article[]"]').value = item.article || '';
    row.querySelector('[name="quantity[]"]').value = item.quantity ?? 1;
    row.querySelector('[name="price[]"]').value = item.price ?? 0;
    row.querySelector('[name="net_price[]"]').value = item.net_price ?? '';
    row.querySelector('[name="discount[]"]').value = item.discount ?? '';
    row.querySelector('[name="discount_percent[]"]').value = item.discount_percent ?? '';
    row.querySelector('[name="line_total[]"]').value = item.total ?? 0;
    row.querySelector('[name="user_name[]"]').value = item.user_name || '';
  }
  bindRow(row);
  bindSuggestions(row);
  refreshTicketTotal();
  const articleInput = row.querySelector('[name="article[]"]');
  if (focusArticle && articleInput) {
    articleInput.focus();
    articleInput.select();
  }
}

function loadInitialTicket() {
  const dataNode = document.getElementById('initial-ticket-data');
  if (!dataNode) {
    addRow();
    return;
  }
  const payload = JSON.parse(dataNode.textContent || '{}');
  const items = Array.isArray(payload.items) ? payload.items : [];
  if (items.length === 0) {
    addRow();
    return;
  }
  items.forEach((item) => addRow(item, { focusArticle: false }));
}

function initChart() {
  const chartNode = document.getElementById('monthly-chart');
  if (!chartNode || typeof Chart === 'undefined') {
    return;
  }
  if (typeof ChartDataLabels !== 'undefined') {
    Chart.register(ChartDataLabels);
  }
  const labels = JSON.parse(chartNode.dataset.labels || '[]');
  const rawDatasets = JSON.parse(chartNode.dataset.datasets || '[]');
  const palette = [
    '#b8d8cc',
    '#f3c99c',
    '#cfc7f6',
    '#bed8ee',
    '#efc1d7',
    '#cde2b2',
    '#f2beb5',
    '#d7dde2',
  ];
  const datasets = rawDatasets.map((dataset, index) => ({
    label: dataset.label,
    data: dataset.data,
    backgroundColor: palette[index % palette.length],
    borderRadius: 12,
  }));
  new Chart(chartNode, {
    type: 'bar',
    data: {
      labels,
      datasets,
    },
    options: {
      responsive: true,
      plugins: {
        datalabels: {
          anchor: 'end',
          align: 'top',
          offset: 2,
          color: '#5a5f52',
          formatter: (value) => (value > 0 ? `${Number(value).toFixed(2)} €` : ''),
          font: {
            size: 10,
            weight: '600',
          },
        },
        legend: {
          display: true,
          position: 'top',
        },
      },
      scales: {
        y: {
          beginAtZero: true,
        },
      },
    },
  });
}

document.addEventListener('DOMContentLoaded', () => {
  const addItemButton = document.getElementById('add-item');
  if (addItemButton) {
    addItemButton.addEventListener('click', () => addRow());
    loadInitialTicket();
  }
  bindSuggestions();
  initChart();
});
