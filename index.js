// index.js

window.addEventListener('DOMContentLoaded', function() {
    var elements = document.querySelectorAll('h3, h4');

    elements.forEach(function(element) {
        var text = element.innerHTML;
        var highlighted = text.replace(/&lt;([^&]+)&gt;/g, '<span class="highlight">&lt;$1&gt;</span>');
        element.innerHTML = highlighted;
    });
});
