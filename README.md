# EU Legal Text OCR Parser
Creates JSON objects from EU Legal text for better AI input.\
When working with Legal Text in the EU people often parse long PDFs into tools like ChatGPT.
However, the PDF parser of those tools, even on premium, seems to hallucinate and/or end parsing those legal text after a certain amount of pages.
That is where this small repo jumps in.
Use the Python file to create machine readable JSON files instead of a PDF. Those files will (very likely) be read in fully by the AI tool and will decrease the liklyhood of hallucinations in your session.

## Usage

1. Install one of the supported PDF backends:

   ```bash
   pip install pdfplumber
   ```

   or

   ```bash
   pip install PyPDF2
   ```

2. Parse one or more PDFs and write the JSON to disk:

   ```bash
   python parser.py GDPR.pdf CRA.pdf output_dir/
   ```

   When providing several PDFs the final argument must be a directory (it will be
   created if it does not yet exist) and each JSON file will be written there,
   reusing the PDF filename with a `.json` extension.

   For a single PDF you can still choose to print the JSON to stdout or write to
   a specific file:

   ```bash
   python parser.py GDPR.pdf GDPR.json
   ```

   Omitting the second argument will print the structured JSON to stdout.

The generated JSON groups recitals ("Whereas" statements), chapters, articles and
their paragraphs so that downstream tools can consume the legal text more
reliably.

Hope this helps.
