<!DOCTYPE html>
<html>

<head>
    <meta charset="utf-8" />
    <title>RustPython Demo</title>
    <link href="styles.css" rel="stylesheet">
</head>

<body>
    <h1>Python Demo</h1>
    <p>
        RustPython is a Python interpreter written in Rust. This demo is
        compiled from Rust to WebAssembly so it runs in the browser.<br>
        Input your Python code below and click <kbd>Run</kbd>
        (or <kbd>Ctrl+Enter</kbd>), or you can open up your
        browser's devtools and play with <code>print(1)</code>
    </p>
    <div id="code-wrapper">
        <textarea id="code">n1 = 0
count = 0
while count < 10:
    print(count)
    count += 1
</textarea>
        <select id="snippets">

            <option>asyncbrowser</option>

            <option>fetch</option>

            <option selected>fibonacci</option>

            <option>fizzbuzz</option>

            <option>mandelbrot</option>

        </select>
    </div>
    <button id="run-btn">Run &#9655;</button>
    <div id="error"></div>
    <h3>Standard Output</h3>
    <textarea id="console" readonly>Loading...</textarea>

    <h3>Interactive shell</h3>
    <div id="terminal"></div>


    <a href=https://github.com/myon-bioinformatics/myon-bioinfotmatics>
        <img style="position: absolute; top: 0; right: 0; border: 0;"
            src="https://avatars.githubusercontent.com/u/54614626?v=4" alt="About me" />
    </a>
    <script type="text/javascript" src="index.js"></script>
</body>

</html>
