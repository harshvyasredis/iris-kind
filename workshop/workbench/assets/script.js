

// State
let panelState = {};
let sidebarVisible = true;
let maximizedPanelId = null;

// Initialize the workbench
function init() {
  // Set title from config
  document.getElementById('title').textContent = config.title;
  document.title = config.title;

  // Initialize panel state from config
  config.panels.forEach(panel => {
    panelState[panel.id] = { visible: panel.visible !== false };
  });

  // Initialize sidebar visibility
  sidebarVisible = config.sidebar.visible !== false;

  // Build the UI
  buildPanels();
  buildMenu();
  setupMenuToggle();
  setupResizers();
}

// Build panels from config
function buildPanels() {
  const main = document.getElementById('container');
  main.innerHTML = '';

  // Create sidebar (if visible)
  if (sidebarVisible) {
    const sidebarUrl = config.sidebar.path;
    const sidebar = document.createElement('aside');
    sidebar.id = 'sidebar';
    sidebar.className = 'panel';
    sidebar.innerHTML = `
      <div class="panel-header">
        <span class="panel-title">${config.sidebar.name}</span>
        <div class="panel-controls">
          <button class="panel-control-btn sidebar-refresh-btn" title="Refresh ${config.sidebar.name}">
            <i class="fa-solid fa-rotate-right"></i>
          </button>
          <a class="panel-control-btn" href="${sidebarUrl}" target="_blank" rel="noopener noreferrer" title="Open in new tab">
            <i class="fa-solid fa-arrow-up-right-from-square"></i>
          </a>
          <button class="panel-control-btn sidebar-hide-btn" title="Hide ${config.sidebar.name}">
            <i class="fa-solid fa-eye-slash"></i>
          </button>
        </div>
      </div>
      <div class="panel-content">
        <div class="panel-loading" data-url="${sidebarUrl}">
          <i class="fa-solid fa-spinner"></i>
          <span>Connecting...</span>
        </div>
        <iframe title="${config.sidebar.name}"></iframe>
      </div>
    `;
    main.appendChild(sidebar);

    // Setup sidebar refresh button
    sidebar.querySelector('.sidebar-refresh-btn').addEventListener('click', () => {
      const loadingEl = sidebar.querySelector('.panel-loading');
      const iframe = sidebar.querySelector('iframe');
      if (iframe && loadingEl) {
        iframe.src = '';
        loadingEl.classList.remove('hidden');
        loadPanelWithRetry(loadingEl);
      }
    });

    // Setup sidebar hide button
    sidebar.querySelector('.sidebar-hide-btn').addEventListener('click', () => {
      toggleSidebarVisibility(false);
      buildMenu(); // Update menu checkbox
    });

    // Create vertical resizer
    const verticalResizer = document.createElement('div');
    verticalResizer.id = 'verticalResizer';
    verticalResizer.className = 'resizer resizer-vertical';
    verticalResizer.innerHTML = '<div class="resizer-handle"></div>';
    main.appendChild(verticalResizer);
  }

  // Create right stack
  const rightStack = document.createElement('div');
  rightStack.className = 'right-stack';
  rightStack.id = 'rightStack';
  main.appendChild(rightStack);

  // Create panels in right stack
  buildRightStack();
}

// Build the right stack panels (called once during init)
function buildRightStack() {
  const rightStack = document.getElementById('rightStack');

  // Create all panels (resizers are added dynamically based on visibility)
  config.panels.forEach((panel) => {
    // Create panel
    const panelUrl = panel.path;
    const section = document.createElement('section');
    section.id = `panel-${panel.id}`;
    section.className = 'panel';
    section.innerHTML = `
      <div class="panel-header">
        <span class="panel-title">${panel.name}</span>
        <div class="panel-controls">
          <button class="panel-control-btn refresh-btn" data-panel="${panel.id}" title="Refresh ${panel.name}">
            <i class="fa-solid fa-rotate-right"></i>
          </button>
          <a class="panel-control-btn" href="${panelUrl}" target="_blank" rel="noopener noreferrer" title="Open in new tab">
            <i class="fa-solid fa-arrow-up-right-from-square"></i>
          </a>
          <button class="panel-control-btn hide-btn" data-panel="${panel.id}" title="Hide ${panel.name}">
            <i class="fa-solid fa-eye-slash"></i>
          </button>
          <button class="panel-control-btn maximize-btn" data-panel="${panel.id}" title="Maximize">
            <i class="fa-solid fa-expand"></i>
          </button>
        </div>
      </div>
      <div class="panel-content">
        <div class="panel-loading" data-url="${panelUrl}">
          <i class="fa-solid fa-spinner"></i>
          <span>Connecting...</span>
        </div>
        <iframe title="${panel.name}"></iframe>
      </div>
    `;
    rightStack.appendChild(section);
  });

  // Setup panel header buttons
  setupPanelHeaderButtons();
  // Setup resizers
  setupResizers();
  // Start checking for panel availability
  startPanelLoaders();
  // Apply initial visibility
  updatePanelVisibility();
}

// Update panel visibility using CSS (preserves iframes)
function updatePanelVisibility() {
  config.panels.forEach((panel) => {
    const section = document.getElementById(`panel-${panel.id}`);
    if (!section) return;

    const isVisible = panelState[panel.id]?.visible;
    const isMaximized = maximizedPanelId === panel.id;
    const shouldShow = isVisible && (!maximizedPanelId || isMaximized);

    // Show/hide panel
    section.style.display = shouldShow ? '' : 'none';
    section.classList.toggle('maximized', isMaximized);

    // Reset flex/height when shown so panels redistribute evenly
    if (shouldShow) {
      section.style.flex = '';
      section.style.height = '';
    }

    // Update maximize button icon
    const maxBtn = section.querySelector('.maximize-btn');
    if (maxBtn) {
      const icon = maxBtn.querySelector('i');
      icon.className = `fa-solid ${isMaximized ? 'fa-compress' : 'fa-expand'}`;
      maxBtn.title = isMaximized ? 'Restore' : 'Maximize';
    }
  });

  // Rebuild resizers between visible adjacent panels
  rebuildHorizontalResizers();
}

// Rebuild horizontal resizers to connect only visible adjacent panels
function rebuildHorizontalResizers() {
  const rightStack = document.getElementById('rightStack');
  if (!rightStack) return;

  // Remove all existing horizontal resizers
  rightStack.querySelectorAll('.resizer-horizontal').forEach(r => r.remove());

  // Don't add resizers if a panel is maximized
  if (maximizedPanelId) return;

  // Get visible panels in config order
  const visiblePanels = config.panels.filter(p => panelState[p.id]?.visible);

  // Insert resizers between adjacent visible panels
  for (let i = 1; i < visiblePanels.length; i++) {
    const abovePanel = visiblePanels[i - 1];
    const belowPanel = visiblePanels[i];

    const resizer = document.createElement('div');
    resizer.className = 'resizer resizer-horizontal';
    resizer.dataset.above = abovePanel.id;
    resizer.dataset.below = belowPanel.id;
    resizer.innerHTML = '<div class="resizer-handle"></div>';

    // Insert before the below panel
    const belowSection = document.getElementById(`panel-${belowPanel.id}`);
    if (belowSection) {
      rightStack.insertBefore(resizer, belowSection);
    }
  }

  // Re-setup resizer event handlers
  setupHorizontalResizers();
}

// Try to load a panel, retry until successful
function loadPanelWithRetry(loadingEl) {
  const url = loadingEl.dataset.url;
  const iframe = loadingEl.parentElement.querySelector('iframe');

  const tryLoad = async () => {
    try {
      await fetch(url, { method: 'HEAD', mode: 'no-cors' });
      // no-cors doesn't give us status, but if it doesn't throw, server is up
      iframe.src = url;
      loadingEl.classList.add('hidden');
    } catch (e) {
      // Server not ready, retry
      setTimeout(tryLoad, 1000);
    }
  };
  tryLoad();
}

// Start loading all panels
function startPanelLoaders() {
  document.querySelectorAll('.panel-loading').forEach(loadingEl => {
    loadPanelWithRetry(loadingEl);
  });
}

// Build the hamburger menu
function buildMenu() {
  const menu = document.getElementById('panelMenu');
  menu.innerHTML = '';

  // Add sidebar to menu first
  const sidebarItem = document.createElement('div');
  sidebarItem.className = 'panel-menu-item';
  sidebarItem.innerHTML = `
    <input type="checkbox" id="menu-sidebar" ${sidebarVisible ? 'checked' : ''}>
    <label for="menu-sidebar">
      <i class="fa-solid ${config.sidebar.icon}"></i>
      ${config.sidebar.name}
    </label>
  `;
  menu.appendChild(sidebarItem);

  const sidebarCheckbox = sidebarItem.querySelector('input');
  sidebarCheckbox.addEventListener('change', () => {
    toggleSidebarVisibility(sidebarCheckbox.checked);
  });

  // Add separator
  const separator = document.createElement('div');
  separator.className = 'panel-menu-separator';
  menu.appendChild(separator);

  // Add right-side panels
  config.panels.forEach(panel => {
    const item = document.createElement('div');
    item.className = 'panel-menu-item';
    item.innerHTML = `
      <input type="checkbox" id="menu-${panel.id}" ${panelState[panel.id]?.visible ? 'checked' : ''}>
      <label for="menu-${panel.id}">
        <i class="fa-solid ${panel.icon}"></i>
        ${panel.name}
      </label>
    `;
    menu.appendChild(item);

    // Handle checkbox change
    const checkbox = item.querySelector('input');
    checkbox.addEventListener('change', () => {
      togglePanelVisibility(panel.id, checkbox.checked);
    });
  });
}

// Toggle sidebar visibility
function toggleSidebarVisibility(visible) {
  sidebarVisible = visible;
  buildPanels();
  setupResizers();
}

// Toggle menu visibility
function setupMenuToggle() {
  const menuButton = document.getElementById('menuButton');
  const menu = document.getElementById('panelMenu');

  menuButton.addEventListener('click', (e) => {
    e.stopPropagation();
    menu.classList.toggle('hidden');
  });

  // Close menu when clicking outside
  document.addEventListener('click', (e) => {
    if (!menu.contains(e.target) && e.target !== menuButton) {
      menu.classList.add('hidden');
    }
  });
}

// Toggle panel visibility
function togglePanelVisibility(panelId, visible) {
  panelState[panelId].visible = visible;

  // If hiding the maximized panel, un-maximize it
  if (!visible && maximizedPanelId === panelId) {
    maximizedPanelId = null;
  }

  // Ensure at least one panel is visible
  const visibleCount = Object.values(panelState).filter(p => p.visible).length;
  if (visibleCount === 0) {
    panelState[panelId].visible = true;
    const checkbox = document.getElementById(`menu-${panelId}`);
    if (checkbox) checkbox.checked = true;
    return;
  }

  updatePanelVisibility();
}

// Setup panel header buttons (maximize, hide, refresh)
function setupPanelHeaderButtons() {
  // Refresh buttons
  document.querySelectorAll('.refresh-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const panelId = btn.dataset.panel;
      const section = document.getElementById(`panel-${panelId}`);
      const loadingEl = section?.querySelector('.panel-loading');
      const iframe = section?.querySelector('iframe');
      if (iframe && loadingEl) {
        iframe.src = '';
        loadingEl.classList.remove('hidden');
        loadPanelWithRetry(loadingEl);
      }
    });
  });

  // Maximize buttons
  document.querySelectorAll('.maximize-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const panelId = btn.dataset.panel;
      if (maximizedPanelId === panelId) {
        maximizedPanelId = null;
      } else {
        maximizedPanelId = panelId;
      }
      updatePanelVisibility();
    });
  });

  // Hide buttons
  document.querySelectorAll('.hide-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const panelId = btn.dataset.panel;
      togglePanelVisibility(panelId, false);
      buildMenu(); // Update menu checkboxes
    });
  });
}

// Disable iframe pointer events during resize
function disableIframePointerEvents() {
  document.querySelectorAll('iframe').forEach(iframe => {
    iframe.style.pointerEvents = 'none';
  });
}

function enableIframePointerEvents() {
  document.querySelectorAll('iframe').forEach(iframe => {
    iframe.style.pointerEvents = 'auto';
  });
}

// Setup vertical resizer (sidebar)
function setupResizers() {
  const main = document.getElementById('container');
  const sidebar = document.getElementById('sidebar');

  const verticalResizer = document.getElementById('verticalResizer');
  if (verticalResizer) {
    const handle = verticalResizer.querySelector('.resizer-handle');
    if (handle) {
      // Remove old listeners by cloning
      const newHandle = handle.cloneNode(true);
      handle.parentNode.replaceChild(newHandle, handle);

      newHandle.addEventListener('mousedown', (e) => {
        e.preventDefault();
        disableIframePointerEvents();
        document.body.style.cursor = 'col-resize';

        const onMouseMove = (e) => {
          const mainRect = main.getBoundingClientRect();
          const offsetX = e.clientX - mainRect.left;
          const newWidth = (offsetX / mainRect.width) * 100;
          if (newWidth > 10 && newWidth < 70) {
            sidebar.style.width = newWidth + '%';
          }
        };

        const onMouseUp = () => {
          document.removeEventListener('mousemove', onMouseMove);
          document.removeEventListener('mouseup', onMouseUp);
          document.body.style.cursor = 'default';
          enableIframePointerEvents();
        };

        document.addEventListener('mousemove', onMouseMove);
        document.addEventListener('mouseup', onMouseUp);
      });
    }
  }

  // Setup horizontal resizers for initial state
  setupHorizontalResizers();
}

// Setup horizontal resizers (between panels in right stack)
function setupHorizontalResizers() {
  document.querySelectorAll('.right-stack .resizer-horizontal').forEach(resizer => {
    const handle = resizer.querySelector('.resizer-handle');
    if (handle) {
      // Remove old listeners by cloning
      const newHandle = handle.cloneNode(true);
      handle.parentNode.replaceChild(newHandle, handle);

      newHandle.addEventListener('mousedown', (e) => {
        e.preventDefault();
        disableIframePointerEvents();
        document.body.style.cursor = 'row-resize';

        const aboveId = resizer.dataset.above;
        const belowId = resizer.dataset.below;
        const abovePanel = document.getElementById(`panel-${aboveId}`);
        const belowPanel = document.getElementById(`panel-${belowId}`);

        if (!abovePanel || !belowPanel) return;

        // Get initial sizes
        const aboveRect = abovePanel.getBoundingClientRect();
        const belowRect = belowPanel.getBoundingClientRect();
        const combinedHeight = aboveRect.height + belowRect.height;
        const startY = e.clientY;
        const startAboveHeight = aboveRect.height;

        const onMouseMove = (e) => {
          const deltaY = e.clientY - startY;
          const newAboveHeight = startAboveHeight + deltaY;
          const newBelowHeight = combinedHeight - newAboveHeight;

          // Minimum height of 50px for each panel
          if (newAboveHeight > 50 && newBelowHeight > 50) {
            abovePanel.style.flex = 'none';
            belowPanel.style.flex = 'none';
            abovePanel.style.height = newAboveHeight + 'px';
            belowPanel.style.height = newBelowHeight + 'px';
          }
        };

        const onMouseUp = () => {
          document.removeEventListener('mousemove', onMouseMove);
          document.removeEventListener('mouseup', onMouseUp);
          document.body.style.cursor = 'default';
          enableIframePointerEvents();
        };

        document.addEventListener('mousemove', onMouseMove);
        document.addEventListener('mouseup', onMouseUp);
      });
    }
  });
}

// Initialize when DOM is ready
init();
