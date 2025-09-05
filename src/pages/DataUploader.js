import React, { useState } from 'react';
import fetchWithRetry from '../utils/fetchWithRetry';

const DataUploader = () => {
  const [files, setFiles] = useState([]);
  const [cleanedData, setCleanedData] = useState(null);
  const [error, setError] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [email, setEmail] = useState('');

  const handleFileChange = (event) => {
    setFiles(event.target.files);
  };

  const handleUpload = async () => {
    if (files.length === 0) {
      setError('Please select one or more files to upload.');
      return;
    }

    setIsLoading(true);
    setError(null);
    setCleanedData(null);

    const formData = new FormData();
    for (let i = 0; i < files.length; i++) {
        formData.append('files', files[i]);
    }

    try {
      const response = await fetchWithRetry('/api/upload_data', {
        method: 'POST',
        body: formData,
      });

      const data = await response.json();

      if (data.error) {
        setError(data.error);
      } else {
        setCleanedData(data.cleaned_data);
      }
    } catch (e) {
      setError(`Error uploading file: ${e.message}`);
    } finally {
      setIsLoading(false);
    }
  };

  const handleDownload = () => {
    if (!cleanedData) {
      return;
    }

    const blob = new Blob([cleanedData], { type: 'text/csv' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'cleaned_data.csv';
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);
  };

  const handleShare = async () => {
    if (!cleanedData) {
        setError('No cleaned data to share.');
        return;
    }
    if (!email) {
        setError('Please enter an email address.');
        return;
    }

    try {
        const response = await fetchWithRetry('/api/share_email', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ email: email, csv_data: cleanedData }),
        });

        const data = await response.json();
        if (data.error) {
            setError(data.error);
        } else {
            alert('Email sent successfully!');
        }
    } catch (e) {
        setError(`Error sharing file: ${e.message}`);
    }
  };

  return (
    <div className="p-4">
      <h2 className="text-2xl font-bold mb-4">Data Uploader</h2>
      <div className="mb-4">
        <input type="file" multiple onChange={handleFileChange} />
        <button onClick={handleUpload} disabled={isLoading} className="ml-2 px-4 py-2 bg-blue-500 text-white rounded">
          {isLoading ? 'Uploading...' : 'Upload and Clean'}
        </button>
      </div>
      {error && <div className="text-red-500">{error}</div>}
      {cleanedData && (
        <div>
          <h3 className="text-xl font-bold mb-2">Cleaned Data</h3>
          <button onClick={handleDownload} className="px-4 py-2 bg-green-500 text-white rounded mb-2">
            Download Cleaned CSV
          </button>
          <div className="flex items-center mb-2">
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="Recipient's Email" className="mr-2 px-2 py-1 border rounded"/>
            <button onClick={handleShare} className="px-4 py-2 bg-purple-500 text-white rounded">
                Share via Email
            </button>
          </div>
          <div className="overflow-x-auto">
            <pre className="bg-gray-100 p-2 rounded">{cleanedData}</pre>
          </div>
        </div>
      )}
    </div>
  );
};

export default DataUploader;
