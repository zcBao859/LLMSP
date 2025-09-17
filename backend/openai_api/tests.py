# backend/openai_api/tests.py
"""
Tests for OpenAI API app
"""
from django.test import TestCase, Client
from django.urls import reverse
from rest_framework import status
import json


class ChatCompletionsTestCase(TestCase):
    """Test chat completions endpoint"""
    
    def setUp(self):
        self.client = Client()
        self.url = reverse('openai_api:chat-completions')
        self.headers = {
            'HTTP_AUTHORIZATION': 'Bearer test-key-1',
            'content_type': 'application/json'
        }
    
    def test_chat_completion_without_auth(self):
        """Test chat completion without authentication"""
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    
    def test_chat_completion_with_invalid_auth(self):
        """Test chat completion with invalid authentication"""
        headers = {
            'HTTP_AUTHORIZATION': 'Bearer invalid-key',
            'content_type': 'application/json'
        }
        response = self.client.post(self.url, **headers)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    
    def test_chat_completion_with_invalid_data(self):
        """Test chat completion with invalid request data"""
        data = {'invalid': 'data'}
        response = self.client.post(
            self.url,
            data=json.dumps(data),
            **self.headers
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class ModelsTestCase(TestCase):
    """Test models endpoints"""
    
    def setUp(self):
        self.client = Client()
        self.list_url = reverse('openai_api:models-list')
        self.headers = {
            'HTTP_AUTHORIZATION': 'Bearer test-key-1'
        }
    
    def test_list_models(self):
        """Test listing models"""
        response = self.client.get(self.list_url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertIn('data', data)
        self.assertEqual(data['object'], 'list')
    
    def test_get_model_detail(self):
        """Test getting model details"""
        url = reverse('openai_api:model-detail', args=['jiutian-model'])
        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data['id'], 'jiutian-model')
        self.assertEqual(data['object'], 'model')


class HealthCheckTestCase(TestCase):
    """Test health check endpoints"""
    
    def test_health_check(self):
        """Test health check endpoint"""
        url = reverse('openai_api:health-check')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data['status'], 'healthy')
        self.assertIn('version', data)
        self.assertIn('timestamp', data)


# backend/openai_api/admin.py
"""
Django admin configuration for OpenAI API app

Note: This app doesn't have database models, so no admin configuration needed.
"""
from django.contrib import admin

# No models to register