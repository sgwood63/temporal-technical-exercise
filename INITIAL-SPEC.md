# Temporal Technical Exercise for Solution Architect hiring process

## Introduction

This project is to respond to the Temporal Technical Exercise and prep for the Technical Interview for a Temporal Solution Architect.

The Technical Exercise is in the "Sherman Wood - SA Technical Interview Handout.pdf"

As stated in the Exercise:
- "You can choose one of the following or choose a use case from your own 
background and "Temporalize" it."
- "This exercise is to prepare for an engaging conversation about how Temporal can solve challenges in distributed services. The goal isn't completeness; it is how you work through this assignment."

Given my data and analytics background, I am going to implement this use case from the Exercise:

**A company wants to understand customer sentiment for one of their products. Write a 
pipeline that scrapes reviews of the product online and runs sentiment analysis on them. 
Average the sentiment scores to get an overall score for the product.**

The first thing I am doing is creating this README as a spec for the work.

I am going to use Claude Code to help with the implementation. I have already used Claude Code to deploy, extend and bug fix the Temporal AI Agent https://github.com/temporal-community/temporal-ai-agent - my repo https://github.com/sgwood63/temporal-getting-started 

## Initial thoughts on implementing the exercise

- This will be a Python script
- I want to use Temporal Cloud. I already have an evaluation account, and used it for temporal-getting-started.
- I want to use Temporal APIs, tools and best practices. Check on the Temporal web site and documentation to see whether there are examples that help with this data integration to analysis use case.
- I want to use Claude Code best practices, like defining a CLAUDE.md
- For this exercise, we will only do one site. Initially will try Amazon and Etsy.
- The sentiment analysis result data needs to be stored in a database. Determine what database and schema would be good for this. I'd like to use Superset to view the data - this is separate from the main exercise.

## Use case workflow design thoughts

1. The script should result in sentiment analysis data being placed in a database for downstream analysis.
2. The use case specifies scraping reviews by product, which implies hitting public ecommerce sites like Amazon. I can imagine that such sites will not like such scraping: requiring authentication, not wanting automated scraping - so the overall process will need to work out the best approach to make the scraping succeed and deal with errors.
3. Scraping each ecommerce web site will have its own challenges. I think there is a GenAI process to be applied to each site to configure scraping, so the script does not have to work it out. Or could a step in the workflow be to configure the scraping process for a site if it has not been seen before? And store the configuration for reuse later.

## Testing

I want tests for the workflows that include occasional and final failures for all the activities. There needs to be an option to test using Temporal Cloud, with indications that these are test workflows.