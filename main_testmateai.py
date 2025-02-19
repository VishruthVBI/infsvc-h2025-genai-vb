from flask import Flask, request, render_template, send_file
import os
import boto3  # AWS SDK for Python
import json
from botocore.exceptions import ClientError
import git
import sys
import shutil
import importlib.util
import unittest
from io import StringIO

app = Flask(__name__)


EXECUTABLE_FOLDER = 'executable_files'
if not os.path.exists(EXECUTABLE_FOLDER):
    os.makedirs(EXECUTABLE_FOLDER)

app.config['EXECUTABLE_FOLDER'] = EXECUTABLE_FOLDER


aws_access_key_id = 'use aws access key id '  
aws_secret_access_key = 'aws access secrets'  

# Initialize AWS Bedrock client
bedrock_client = boto3.client(
    'bedrock-runtime',
    region_name='us-east-1',
    aws_access_key_id=aws_access_key_id,
    aws_secret_access_key=aws_secret_access_key
)

@app.route('/')
def upload_form():
    return render_template('upload_github.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    # Get GitHub information
    github_url = request.form.get('github_url')
    git_access_token = request.form.get('git_access_token')

    code_files = []
    supporting_files = []

    # Remove any existing files in EXECUTABLE_FOLDER to avoid conflicts
    if os.path.exists(EXECUTABLE_FOLDER):
        shutil.rmtree(EXECUTABLE_FOLDER)
    os.makedirs(EXECUTABLE_FOLDER)

    # Clone GitHub repository if URL is provided
    if github_url:
        try:
            # GitHub uses OAuth or token for authentication - use the access token
            repo_name = github_url.split('/')[-1].replace('.git', '')
            repo_path = os.path.join(app.config['EXECUTABLE_FOLDER'], repo_name)


            repo_url_with_token = github_url.replace('https://', f'https://{git_access_token}@')

            # Clone the GitHub repository using the token
            git.Repo.clone_from(repo_url_with_token, repo_path)

            # Traverse the repository and get all Python files and supporting files
            for root, _, filenames in os.walk(repo_path):
                for filename in filenames:
                    file_path = os.path.join(root, filename)
                    # Copy all files to EXECUTABLE_FOLDER
                    shutil.copy(file_path, app.config['EXECUTABLE_FOLDER'])
                    if filename.endswith('.py'):
                        code_files.append(file_path)
                    elif filename.endswith(('.csv', '.xlsx')):
                        supporting_files.append(file_path)

        except Exception as e:
            return f"Error cloning repository: {e}"

    # Handle uploaded files as well
    files = request.files.getlist('files[]')
    for file in files:
        if file.filename != '':
            file_path = os.path.join(app.config['EXECUTABLE_FOLDER'], file.filename)
            file.save(file_path)
            if file.filename.endswith(('.py', '.js', '.scala')):
                code_files.append(file_path)
            elif file.filename.endswith(('.csv', '.xlsx')):
                supporting_files.append(file_path)


    if not code_files:
        return "Please provide at least one code file or a GitHub repository containing code files."

    # Generate test cases using AWS Bedrock client
    generated_tests = generate_test_cases(code_files, supporting_files)

    # Save the generated tests to a .py file in EXECUTABLE_FOLDER
    test_file_path = os.path.join(app.config['EXECUTABLE_FOLDER'], 'generated_tests.py')
    with open(test_file_path, 'w') as test_file:
        # Save the generated test for each uploaded file
        for filename, tests in generated_tests.items():
            test_file.write(tests + '\n\n')

    return render_template('results.html', generated_tests=generated_tests)

def generate_test_cases(file_paths, supporting_files):
    generated_tests = {}
    # Group files by extension
    file_groups = {"py": [], "js": [], "scala": []}

    for file_path in file_paths:
        _, file_extension = os.path.splitext(file_path)
        file_extension = file_extension.lstrip(".")  # Remove leading dot

        if file_extension in file_groups:
            file_groups[file_extension].append(file_path)


    selected_files = []
    for ext, files in file_groups.items():
        selected_files.extend(files[:3])  # Select up to 3 files per type
        
    # Create a dictionary to hold the content of all files
    file_contents = {}
    for file_path in selected_files:
        with open(file_path, 'r') as f:
            file_contents[file_path] = f.read()

    for file_path in selected_files:
        module_name, file_extension = os.path.splitext(os.path.basename(file_path))
        code_content = file_contents[file_path]

        # Create the prompt for test case generation
        if file_extension == ".py":
            prompt = f"""
            Here is a Python file named '{os.path.basename(file_path)}'.  

            **Task:**  
            - Generate exactly **3 Python unit tests** for function(s) in '{os.path.basename(file_path)}'.  
            - The test cases should be **simple and self-contained**.  
            - you should not import any of the files or modules from dependency filesunitest must use file logic but it should be generic testcases
            - **DO NOT import this file (`{os.path.basename(file_path)}`).**  
            - **DO NOT test user input (`input()`).**  
            - **DO NOT interact with APIs, databases, or external files.**  
            - The tests should focus **only on isolated logic**, such as:
            - String processing
            - Conditional logic (if-else statements)
            - Loops
            - Basic calculations

            **Test Generation Instructions:**  
            - Extract logic that can be tested independently.
            - **DO NOT assume the function exists in a separate file.**
            - Instead, **define the function inside the test file** as a local version before testing.

            **Code to generate tests for:**  
            {code_content}


            Please provide only the Python code for the generated test cases, without any additional comments or explanations.
            """


        elif file_extension == ".js":
            prompt = f"""
            Here is a JavaScript file named '{os.path.basename(file_path)}'. 
            Generate Python unit tests for the function(s) .
            Ensure the tests cover edge cases and include clear assertions.
            Do not include imports from non-Python files. Provide only Python code for the function and the test cases.It should be simple.

            Code to generate tests for:
            {code_content}

            Please provide only the Python code for the generated test cases, without any additional comments or explanations.
            """
        elif file_extension == ".scala":
            prompt = f"""
            Here is a Scala file named '{os.path.basename(file_path)}'. 
            Generate Python unit tests for the function(s) 
            Ensure the tests cover edge cases and include clear assertions.
            Do not include imports from non-Python files. Provide only Python code for the function and the test cases.It should be simple.
            
            
            - The test cases should be **simple and self-contained**.  
            - **DO NOT import this file (`{os.path.basename(file_path)}`).**  
            - **DO NOT test user input (`input()`).**  
            - **DO NOT interact with APIs, databases, or external files.**  
            - use unitest module & based on that write testcases
            - The tests should focus **only on isolated logic**, such as:
            - String processing
            - Conditional logic (if-else statements)
            - Loops
            - Basic calculations

            **Test Generation Instructions:**  
            - Extract logic that can be tested independently.
            - **DO NOT assume the function exists in a separate file.**
            - Instead, **define the function inside the test file** as a local version before testing.
            
            Code to generate tests for:
            {code_content}

            Please provide only the Python code for the generated test cases, without any additional comments or explanations.
            """
        else:
         
            continue

        formatted_prompt = f"Human: {prompt}\nAssistant:"

  
        native_request = {
            "prompt": formatted_prompt,
            "max_tokens_to_sample": 1024,
            "temperature": 0.5,
        }

     
        request_payload = json.dumps(native_request)

        try:
          
            response = bedrock_client.invoke_model(
                modelId="anthropic.claude-instant-v1",
                contentType="application/json",
                accept="application/json",
                body=request_payload
            )

        
            model_response = json.loads(response["body"].read())
            response_text = model_response.get("completion")

            if response_text is not None:
               
                cleaned_response = response_text.strip()
                # Add the cleaned response to the generated tests dictionary
                generated_tests[file_path] = cleaned_response
            else:
                generated_tests[file_path] = "# No response generated."

        except (ClientError, Exception) as e:
            print(f"ERROR: Can't invoke the model. Reason: {e}")
            generated_tests[file_path] = f"# No response generated due to an error for file {file_path}."

    return generated_tests


import subprocess
import sys
import importlib.util



@app.route('/download_output', methods=['POST'])
def download_output():
    # Path for saving the HTML report
    output_file_path = os.path.join(app.config['EXECUTABLE_FOLDER'], 'test_output.txt')

    # Content to include in the HTML file for download
    with open(output_file_path, 'w') as file:
        output = file.write()
    # Create a colorful HTML report
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>TestMate AI - Test Results</title>
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/bootstrap/5.1.3/css/bootstrap.min.css">
        <style>
            body {{
                background-color: #f8f9fa;
                font-family: Arial, sans-serif;
                overflow-x: hidden;
            }}
            .container {{
                max-width: 800px;
                margin-top: 50px;
                padding: 20px;
                background-color: #ffffff;
                border-radius: 10px;
                box-shadow: 0 0 15px rgba(0, 0, 0, 0.1);
                animation: fadeIn 2s ease-in-out;
            }}
            .header {{
                background: linear-gradient(90deg, #007bff, #28a745, #ffc107);
                background-size: 300% 300%;
                color: white;
                padding: 10px;
                text-align: center;
                border-radius: 10px;
                font-size: 24px;
                font-weight: bold;
                animation: gradientAnimation 6s ease infinite;
            }}
            pre {{
                background-color: #f1f1f1;
                padding: 15px;
                border-radius: 5px;
                overflow: auto;
                animation: slideIn 1.5s ease-in-out;
            }}
            @keyframes gradientAnimation {{
                0% {{ background-position: 0% 50%; }}
                50% {{ background-position: 100% 50%; }}
                100% {{ background-position: 0% 50%; }}
            }}
            @keyframes fadeIn {{
                0% {{ opacity: 0; transform: translateY(-20px); }}
                100% {{ opacity: 1; transform: translateY(0); }}
            }}
            @keyframes slideIn {{
                0% {{ opacity: 0; transform: translateX(-20px); }}
                100% {{ opacity: 1; transform: translateX(0); }}
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">TestMate AI Report</div>
            <h2 class="text-center mt-4">Test Results</h2>
            <pre>{output}</pre>
        </div>
    </body>
    </html>
    """

    # Write the HTML content to the report file
    with open(output_file_path, 'w') as report_file:
        report_file.write(html_content)

    # Send the report file for download
    return send_file(output_file_path, as_attachment=True, download_name='TestMateAI_TestResults.html')



@app.route('/run_tests', methods=['POST'])
def run_tests():

    test_file_path = os.path.abspath(os.path.join(app.config['EXECUTABLE_FOLDER'], 'generated_tests.py'))


    def add_all_subdirs_to_syspath(folder_path):
        """Helper function to add all subdirectories to sys.path."""
        for root, dirs, files in os.walk(folder_path):
            if root not in sys.path:
                sys.path.append(root)


    executable_full_path = os.path.abspath(app.config['EXECUTABLE_FOLDER'])
    add_all_subdirs_to_syspath(executable_full_path)

    # Ensure that all CSV and XLSX files are in the current directory before running tests
    for file in os.listdir(app.config['EXECUTABLE_FOLDER']):
        if file.endswith('.csv') or file.endswith('.xlsx'):
            shutil.copy(os.path.join(app.config['EXECUTABLE_FOLDER'], file), os.getcwd())

    # Identify and install missing third-party dependencies
    try:
        with open(test_file_path, 'r') as test_file:
            # List of built-in modules to ignore for installation
            builtin_modules = set(sys.builtin_module_names)
            imported_modules = set()

            # Scan the file for import statements
            for line in test_file:
                if line.startswith("import ") or line.startswith("from "):
                    package_name = line.split()[1].split('.')[0]
                    imported_modules.add(package_name)

            # Install third-party dependencies
            for module in imported_modules:
                # Skip built-in modules and custom modules
                if module in builtin_modules or module in os.listdir(app.config['EXECUTABLE_FOLDER']):
                    continue

                # Install the package using pip if it's a third-party library
                try:
                    subprocess.run([sys.executable, "-m", "pip", "install", module], check=True)
                except subprocess.CalledProcessError as e:
                    print(f"WARNING: Could not install package '{module}'. Error: {e}")

    except Exception as e:
        return f"An error occurred while installing dependencies: {e}"

    # Store the initial working directory to reset after running the tests
    initial_working_directory = os.getcwd()

    # Load and run the saved .py file
    try:
   
        os.chdir(app.config['EXECUTABLE_FOLDER'])

        # Create a custom StringIO stream to capture the output of the test
        stream = StringIO()
        loader = unittest.TestLoader()

        # Dynamically import the generated test module
        spec = importlib.util.spec_from_file_location("generated_tests", test_file_path)
        generated_tests = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(generated_tests)

        # Load tests from the generated test module
        suite = loader.loadTestsFromModule(generated_tests)
        runner = unittest.TextTestRunner(stream=stream, verbosity=2)
        result = runner.run(suite)

        # Get the output from the stream
        output = stream.getvalue()

    except Exception as e:
        output = f"An error occurred while running the test cases: {e}"

    finally:
        # Reset the working directory to the initial directory after running tests
        os.chdir(initial_working_directory)

    # Return the result page with the test output
    return render_template('test_results.html', output=output)

if __name__ == '__main__':
    app.run(port=5001,debug=False)
