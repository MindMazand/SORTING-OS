using System;
using System.Collections.Generic;

namespace Mazandasht.Domain
{
    /// <summary>
    /// Stable system codes with changeable display names (Spec ch. 4.2).
    /// Prefixes: C, SL, S, E, X, F, L, CAP, BANK, G, SG, WG, T, OP, PB, PS,
    /// BK, W, P. New codes are generated transactionally with uniqueness
    /// control (the DB UNIQUE constraint is the final guard).
    /// </summary>
    public static class PartyNature
    {
        public const string Customer = "C";
        public const string Vendor = "SL";
        public const string Supplier = "S";
        public const string Employee = "E";
        public const string Other = "X";
        public const string FixedAsset = "F";
        public const string Loan = "L";
        public const string Capital = "CAP";

        public static readonly IReadOnlyList<string> All = new[]
        {
            Customer, Vendor, Supplier, Employee, Other, FixedAsset, Loan, Capital
        };

        public static bool IsValid(string nature) =>
            nature != null && ((IList<string>)All).Contains(nature);
    }

    /// <summary>
    /// G-01: the 01_Parties import template classifies every party as PERSON or
    /// COMPANY. That is a legal-entity axis, NOT the account-class axis encoded
    /// in the stable code prefix (PartyNature). The two must never be merged:
    /// merging them would either break the code system or lose the template's
    /// vocabulary. Hence a separate type, validated separately.
    /// </summary>
    public static class PartyKind
    {
        public const string Person = "PERSON";
        public const string Company = "COMPANY";

        public static readonly IReadOnlyList<string> All = new[] { Person, Company };

        public static bool IsValid(string kind) =>
            kind != null && ((IList<string>)All).Contains(kind);
    }

    /// <summary>Generates the next code for a prefix: e.g. S + 001 -> S002.</summary>
    public static class CodeGenerator
    {
        public static string Next(string prefix, int nextNumber, int width = 3)
        {
            if (string.IsNullOrEmpty(prefix)) throw new ArgumentException("Prefix is required.", nameof(prefix));
            if (nextNumber < 1) throw new ArgumentOutOfRangeException(nameof(nextNumber));
            return prefix + nextNumber.ToString("D" + width);
        }

        public static string NextBankCode(int nextNumber) => Next("BANK", nextNumber, 2);
        public static string NextBasketCode(int nextNumber) => Next("BK", nextNumber, 2);
        public static string NextWarehouseCode(int nextNumber) => Next("W", nextNumber, 2);
    }
}
