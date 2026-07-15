const DEFAULT_BACKEND_URL = 'http://localhost:8000';
const BASE_URL = (process.env.NEXT_PUBLIC_API_URL || DEFAULT_BACKEND_URL).replace(/\/$/, '');

function buildUrl(path: string): string {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  return `${BASE_URL}${normalizedPath}`;
}

function getHeaders(isMultipart = false): HeadersInit {
  const headers: Record<string, string> = {};
  if (!isMultipart) {
    headers['Content-Type'] = 'application/json';
  }
  
  if (typeof window !== 'undefined') {
    const token = localStorage.getItem('auth_token');
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }
  }
  return headers;
}

async function handleResponse(response: Response) {
  if (!response.ok) {
    let errorMsg = 'An error occurred';
    try {
      const errData = await response.json();
      errorMsg = errData.message || errData.detail || JSON.stringify(errData);
    } catch {
      errorMsg = response.statusText;
    }
    throw new Error(errorMsg);
  }
  return response.json();
}

export const apiClient = {
  get: async (url: string, options?: RequestInit) => {
    const response = await fetch(buildUrl(url), {
      method: 'GET',
      headers: getHeaders(),
      ...options,
    });
    return handleResponse(response);
  },

  post: async (url: string, data?: unknown, options?: RequestInit) => {
    const response = await fetch(buildUrl(url), {
      method: 'POST',
      headers: getHeaders(),
      body: data !== undefined ? JSON.stringify(data) : undefined,
      ...options,
    });
    return handleResponse(response);
  },

  patch: async (url: string, data?: unknown, options?: RequestInit) => {
    const response = await fetch(buildUrl(url), {
      method: 'PATCH',
      headers: getHeaders(),
      body: data !== undefined ? JSON.stringify(data) : undefined,
      ...options,
    });
    return handleResponse(response);
  },

  postMultipart: async (url: string, formData: FormData, options?: RequestInit) => {
    const response = await fetch(buildUrl(url), {
      method: 'POST',
      headers: getHeaders(true),
      body: formData,
      ...options,
    });
    return handleResponse(response);
  }
};
