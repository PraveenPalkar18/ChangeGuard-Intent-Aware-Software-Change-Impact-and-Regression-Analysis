"""Unit tests for UniversalCodeParser multi-language AST parsing."""
import pytest
from backend.app.repository.universal_parser import UniversalCodeParser
from backend.app.repository.models import CodeEntityType


@pytest.fixture
def parser():
    return UniversalCodeParser()


def test_python_parsing(parser):
    code = """
import os
from math import sqrt

class GeometryCalculator:
    def compute_hypotenuse(self, a, b):
        return sqrt(a**2 + b**2)
"""
    res = parser.parse_source("calc.py", code)
    assert res.is_success
    assert res.language == "python"
    assert len(res.entities) == 2
    assert len(res.imports) == 2
    assert len(res.call_sites) >= 1
    assert any(e.name == "GeometryCalculator" for e in res.entities)
    assert any(e.name == "compute_hypotenuse" for e in res.entities)


def test_javascript_parsing(parser):
    code = """
const mongoose = require("mongoose");
const { calculateDeadlineStatus } = require("../utils/project-tracker");

class ProjectService {
    async getSummary(id) {
        return calculateDeadlineStatus(id);
    }
}

function validateProject(data) {
    return true;
}

const updateStatus = (id) => {
    validateProject(id);
};
"""
    res = parser.parse_source("service.js", code)
    assert res.is_success
    assert res.language == "javascript"
    assert len(res.entities) >= 3
    assert len(res.imports) >= 2
    assert len(res.call_sites) >= 1
    names = [e.name for e in res.entities]
    assert "ProjectService" in names
    assert "validateProject" in names


def test_typescript_parsing(parser):
    code = """
import { Request, Response } from "express";

interface ProjectDTO {
    id: string;
    title: string;
}

export class ProjectController {
    public async handleGet(req: Request, res: Response): Promise<void> {
        this.renderView();
    }

    private renderView(): void {}
}
"""
    res = parser.parse_source("controller.ts", code)
    assert res.is_success
    assert res.language == "typescript"
    assert len(res.entities) >= 2
    assert len(res.imports) >= 1


def test_go_parsing(parser):
    code = """
package main

import (
    "fmt"
    "strings"
)

type Worker struct {
    Name string
}

func (w *Worker) Process() string {
    fmt.Println(w.Name)
    return strings.TrimSpace(w.Name)
}

func NewWorker(name string) *Worker {
    return &Worker{Name: name}
}
"""
    res = parser.parse_source("main.go", code)
    assert res.is_success
    assert res.language == "go"
    assert len(res.entities) >= 2
    assert len(res.imports) >= 1
    names = [e.name for e in res.entities]
    assert "Worker" in names or any("Worker" in e.id for e in res.entities)


def test_java_parsing(parser):
    code = """
package com.example.service;

import java.util.List;

public class OrderProcessor {
    public void processOrder(int orderId) {
        validateOrder(orderId);
    }

    private boolean validateOrder(int id) {
        return id > 0;
    }
}
"""
    res = parser.parse_source("OrderProcessor.java", code)
    assert res.is_success
    assert res.language == "java"
    assert len(res.entities) >= 2
    assert len(res.imports) >= 1
    names = [e.name for e in res.entities]
    assert "OrderProcessor" in names


def test_rust_parsing(parser):
    code = """
use std::collections::HashMap;

pub struct CacheManager {
    data: HashMap<String, String>,
}

impl CacheManager {
    pub fn get_value(&self, key: &str) -> Option<&String> {
        self.data.get(key)
    }
}

pub fn initialize_cache() -> CacheManager {
    CacheManager { data: HashMap::new() }
}
"""
    res = parser.parse_source("cache.rs", code)
    assert res.is_success
    assert res.language == "rust"
    assert len(res.entities) >= 2
    assert len(res.imports) >= 1


def test_csharp_parsing(parser):
    code = """
using System;
using System.Collections.Generic;

namespace ShopApp.Services
{
    public class PaymentHandler
    {
        public bool ProcessPayment(double amount)
        {
            ValidateAmount(amount);
            return true;
        }

        private void ValidateAmount(double amt) {}
    }
}
"""
    res = parser.parse_source("PaymentHandler.cs", code)
    assert res.is_success
    assert res.language == "csharp"
    assert len(res.entities) >= 2
    assert len(res.imports) >= 1


def test_generic_fallback_ruby(parser):
    code = """
require 'json'

class ReportGenerator
  def generate_report
    calculate_totals()
  end
end
"""
    res = parser.parse_source("report.rb", code)
    assert res.is_success
    assert res.language == "generic"
    assert len(res.entities) >= 2
    assert len(res.imports) >= 1


def test_unsupported_binary_file(parser):
    res = parser.parse_source("logo.png", "")
    assert not res.is_success
    assert res.language == "unsupported"

