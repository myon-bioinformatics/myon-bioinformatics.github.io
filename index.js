// index.js

// Wait for the DOM content to load
window.addEventListener('DOMContentLoaded', function () {
    // Select all h3 and h4 elements
    var elements = document.querySelectorAll('h3, h4');

    // Iterate through each element
    elements.forEach(function (element) {
        // Get the innerHTML of the element
        var text = element.innerHTML;

        // Replace '&lt;' and '&gt;' with highlighted spans
        var highlighted = text.replace(/&lt;([^&]+)&gt;/g, '<span class="highlight">&lt;$1&gt;</span>');

        // Update the innerHTML with the highlighted text
        element.innerHTML = highlighted;
    });
});
