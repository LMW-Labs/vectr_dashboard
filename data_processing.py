
import pandas as pd
import io

def clean_data(file_content, file_name):
    """
    Cleans the uploaded data file.
    """
    try:
        file_extension = file_name.split('.')[-1].lower()
        if file_extension == 'csv':
            # For CSV, decode the content from bytes to string
            df = pd.read_csv(io.StringIO(file_content.decode('utf-8')))
        elif file_extension in ['xls', 'xlsx']:
            df = pd.read_excel(io.BytesIO(file_content), engine='openpyxl')
        elif file_extension == 'json':
            # For JSON, decode the content from bytes to string
            df = pd.read_json(io.StringIO(file_content.decode('utf-8')))
        else:
            return None, "Unsupported file type"
    except Exception as e:
        return None, f"Error reading file: {e}"


    # Missing Value Handling (simple example: drop rows with null values)
    df.dropna(inplace=True)

    # Deduplication
    df.drop_duplicates(inplace=True)

    # Format Standardization (example: convert all text to lowercase)
    for col in df.select_dtypes(include=['object']):
        df[col] = df[col].str.lower()
        df[col] = df[col].str.strip()

    return df, None

def get_cleaned_data_as_csv(df):
    """
    Returns the cleaned data as a CSV string.
    """
    output = io.StringIO()
    df.to_csv(output, index=False)
    return output.getvalue()
