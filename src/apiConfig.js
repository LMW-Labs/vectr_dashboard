const getApiUrl = () => {
  return process.env.REACT_APP_API_URL || 'https://py-vectr-backend--vectr-dashboard.us-central1.hosted.app';
};

export default getApiUrl;
