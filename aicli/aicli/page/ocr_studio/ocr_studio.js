frappe.pages['ocr-studio'].on_page_load = function(wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'OCR Studio',
		single_column: true
	});

	let $container = $(wrapper).find('.layout-main-section');
	$container.html('<div id="app">Loading OCR Studio...</div>');

	// Clear out any padding so the app can take full space if needed
	$container.css({ padding: '0px' });
	$(wrapper).find('.page-head').hide(); // Hide Frappe's default page header to let Vue handle it

	fetch('/assets/aicli/index.html')
		.then(response => response.text())
		.then(html => {
			let parser = new DOMParser();
			let doc = parser.parseFromString(html, 'text/html');
			
			$container.empty();
			
			// Inject styles
			doc.querySelectorAll('link[rel="stylesheet"]').forEach(link => {
				let href = link.getAttribute('href');
				if (!$(`link[href="${href}"]`).length) {
					$('<link>').attr('rel', 'stylesheet').attr('href', href).appendTo('head');
				}
			});

			// Inject app div
			let appDiv = doc.querySelector('#app');
			if (appDiv) {
				$container.append(appDiv);
			} else {
				$container.append('<div id="app"></div>');
			}

			// Inject scripts
			doc.querySelectorAll('script').forEach(script => {
				let src = script.getAttribute('src');
				if (src && !$(`script[src="${src}"]`).length) {
					let newScript = document.createElement('script');
					newScript.src = src;
					if (script.type) newScript.type = script.type;
					if (script.crossOrigin) newScript.crossOrigin = script.crossOrigin;
					document.body.appendChild(newScript);
				}
			});
		})
		.catch(err => {
			console.error("Failed to load OCR Studio:", err);
			$container.html('<div class="alert alert-danger">Failed to load OCR Studio application.</div>');
		});
}